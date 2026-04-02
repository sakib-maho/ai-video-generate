from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .content import ContentService
from .fact_check import FactCheckService
from .images import SceneImageService
from .logging_utils import PipelineLogger
from .models import (
    CountryRunArtifacts,
    FactCheckReport,
    PipelineConfig,
    Scene,
    ScriptPackage,
    SelectedTopic,
    SeoPackage,
    ThumbnailPackage,
    TopicCandidate,
    TopicSource,
    VideoRenderRequest,
    to_dict,
)
from .storage import Storage
from .thumbnail import ThumbnailRenderer
from .trends import TrendDiscoveryService
from .utils import ensure_dir, now_local, slugify, write_json, write_text
from .video import VideoService
from .voice import VoiceService


EVERGREEN_TOPICS: dict[str, dict[str, str]] = {
    "bangladesh": {
        "title": "How daily life in Bangladesh is changing with new digital services",
        "why_trending": "Evergreen fallback focused on practical change, public interest, and easy visual storytelling.",
    },
    "japan": {
        "title": "Why everyday technology trends in Japan keep shaping global attention",
        "why_trending": "Evergreen fallback focused on explainable tech and culture signals with safe short-form appeal.",
    },
}


class DailyVideoPipeline:
    def __init__(self, project_root: Path, config: PipelineConfig) -> None:
        self.project_root = project_root
        self.config = config
        self.storage = Storage(project_root / config.database_path)
        self.content_service = ContentService(project_root)
        self.fact_check_service = FactCheckService(project_root)
        self.scene_image_service = SceneImageService(project_root)
        self.thumbnail_renderer = ThumbnailRenderer()
        self.video_service = VideoService(project_root)
        self.voice_service = VoiceService(project_root)

    def run(self, use_sample_data: bool = False) -> dict[str, Any]:
        run_date = now_local().date().isoformat()
        output_dir = ensure_dir(self.project_root / self.config.output_root / run_date)
        logger = PipelineLogger(output_dir, self.config.log_level)
        discovery = TrendDiscoveryService(project_root=self.project_root, logger=logger)
        run_id = self.storage.create_run(run_date=run_date, mode=self.config.mode)
        logger.info(f"Starting pipeline for {run_date} in {self.config.mode} mode")
        provider_status = self.check_providers(logger=logger, raise_on_error=False)

        summary: dict[str, Any] = {
            "run_date": run_date,
            "mode": self.config.mode,
            "countries": {},
            "status": "running",
            "provider_status": provider_status,
        }

        try:
            artifacts: dict[str, CountryRunArtifacts] = {}
            for country in self.config.countries:
                if not country.enabled:
                    continue

                candidates = discovery.discover(country=country, use_sample_data=use_sample_data)
                self._fact_check_candidates(candidates, logger)
                selected = self._select_topic(country.name, candidates)
                if not selected and self.config.global_defaults.evergreen_fallback:
                    selected = self._build_evergreen_topic(country.name, logger)
                    if selected:
                        report = self.fact_check_service.evaluate(selected.candidate)
                        self._attach_fact_check_report(selected.candidate, report)
                for candidate in candidates:
                    self.storage.record_candidate(
                        run_date,
                        candidate,
                        selected=bool(selected and candidate.signature == selected.candidate.signature),
                        status="selected" if selected and candidate.signature == selected.candidate.signature else "discovered",
                    )
                if not selected:
                    logger.warning(f"No safe topic selected for {country.name}")
                    summary["countries"][country.name] = {"status": "skipped", "reason": "no_safe_topic"}
                    continue

                country_dir = ensure_dir(output_dir / country.name)
                artifact = self._generate_country_assets(run_date, country_dir, selected, logger)
                artifacts[country.name] = artifact
                summary["countries"][country.name] = {
                    "status": "prepared" if self.config.mode == "review" else "rendered",
                    "topic": selected.candidate.title,
                    "trend_score": selected.candidate.trend_score,
                    "final_title": artifact.seo.final_title,
                    "language": selected.language,
                    "fact_check_status": selected.candidate.fact_check_status,
                }

            review_packet = self._write_review_packet(output_dir, artifacts)
            summary["review_packet"] = str(review_packet)

            if self.config.mode == "review":
                summary["status"] = "awaiting_review"
                write_json(output_dir / "run_summary.json", summary)
                self.storage.finish_run(run_id, "awaiting_review", summary)
                logger.info("Review mode enabled; skipped final render")
                return summary

            for country_name, artifact in artifacts.items():
                self._render_country_video(run_date, artifact, output_dir / country_name, logger)

            summary["status"] = "completed"
            write_json(output_dir / "run_summary.json", summary)
            self.storage.finish_run(run_id, "completed", summary)
            logger.info("Pipeline completed")
            return summary
        except Exception as exc:
            summary["status"] = "failed"
            summary["error"] = str(exc)
            write_json(output_dir / "run_summary.json", summary)
            self.storage.finish_run(run_id, "failed", summary)
            logger.error(f"Pipeline failed: {exc}")
            raise

    def approve_and_render(self, run_date: str) -> None:
        output_dir = self.project_root / self.config.output_root / run_date
        logger = PipelineLogger(output_dir, self.config.log_level)
        review_path = output_dir / "review_packet.json"
        if not review_path.exists():
            raise FileNotFoundError(f"Review packet not found for {run_date}")
        review_data = json.loads(review_path.read_text(encoding="utf-8"))
        for country_name, country_data in review_data["countries"].items():
            country_dir = output_dir / country_name
            artifact = self._load_artifact_from_disk(country_dir, country_data)
            self._render_country_video(run_date, artifact, country_dir, logger)
        summary_path = output_dir / "run_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"run_date": run_date}
        summary["status"] = "completed"
        write_json(summary_path, summary)

    def check_providers(self, logger: PipelineLogger | None = None, raise_on_error: bool = False) -> dict[str, Any]:
        status: dict[str, Any] = {}

        content_provider = self.content_service.resolve_provider(
            self.config.content_provider.primary,
            self.config.content_provider.fallback,
        )
        if hasattr(content_provider, "validate_access") and content_provider.name != "template":
            try:
                status["content"] = getattr(content_provider, "validate_access")()
            except Exception as exc:
                status["content"] = {"provider": content_provider.name, "status": "error", "error": str(exc)}
                if logger:
                    logger.warning(f"Content provider validation failed: {exc}")
                if raise_on_error:
                    raise
        else:
            status["content"] = {"provider": content_provider.name, "status": "fallback"}

        voice_provider = self.voice_service.resolve_provider()
        if hasattr(voice_provider, "validate_access") and voice_provider.name != "noop":
            try:
                status["voice"] = getattr(voice_provider, "validate_access")()
            except Exception as exc:
                status["voice"] = {"provider": voice_provider.name, "status": "error", "error": str(exc)}
                if logger:
                    logger.warning(f"Voice provider validation failed: {exc}")
                if raise_on_error:
                    raise
        else:
            status["voice"] = {"provider": voice_provider.name, "status": "fallback"}

        if logger:
            logger.event("provider_check", status)
        return status

    def _select_topic(self, country_name: str, candidates: list[TopicCandidate]) -> SelectedTopic | None:
        country = next(item for item in self.config.countries if item.name == country_name)

        for candidate in candidates:
            candidate.duplicate_recently_used = self.storage.was_recently_used(
                signature=candidate.signature,
                country=country_name,
                cooldown_days=self.config.global_defaults.history_cooldown_days,
            )
        ranked = sorted(candidates, key=lambda item: item.trend_score, reverse=True)

        fresh_candidates = [
            candidate
            for candidate in ranked
            if not candidate.duplicate_recently_used
            and candidate.fact_check_status != "unsafe"
            and candidate.trend_score >= self.config.global_defaults.safety_threshold
        ]
        if fresh_candidates:
            return SelectedTopic(
                candidate=fresh_candidates[0],
                language=country.default_language,
                tone=self.config.global_defaults.tone,
                duration_seconds=self.config.global_defaults.script_duration_seconds,
            )

        fallback_candidates = [
            candidate
            for candidate in ranked
            if candidate.fact_check_status != "unsafe"
            and candidate.trend_score >= self.config.global_defaults.safety_threshold
        ]
        if fallback_candidates:
            return SelectedTopic(
                candidate=fallback_candidates[0],
                language=country.default_language,
                tone=self.config.global_defaults.tone,
                duration_seconds=self.config.global_defaults.script_duration_seconds,
            )
        return None

    def _build_evergreen_topic(self, country_name: str, logger: PipelineLogger) -> SelectedTopic | None:
        country = next(item for item in self.config.countries if item.name == country_name)
        seed = EVERGREEN_TOPICS.get(country_name)
        if not seed:
            return None
        candidate = TopicCandidate(
            title=seed["title"],
            country=country_name,
            signature=f"evergreen {country_name}",
            sources=[TopicSource(name="Evergreen fallback", source_type="evergreen", url="local://evergreen")],
            why_trending=seed["why_trending"],
            published_at=now_local(),
            source_count=1,
            trend_score=max(self.config.global_defaults.safety_threshold, 55.0),
            freshness_score=0.0,
            suitability_score=18.0,
            risk_flags=[],
            risk_score=0.0,
            fact_check_status="verified",
            citations=["local://evergreen"],
            extra={"fallback": "evergreen"},
        )
        logger.warning(f"No fresh safe topic for {country_name}; using evergreen fallback")
        return SelectedTopic(
            candidate=candidate,
            language=country.default_language,
            tone=self.config.global_defaults.tone,
            duration_seconds=self.config.global_defaults.script_duration_seconds,
        )

    def _fact_check_candidates(self, candidates: list[TopicCandidate], logger: PipelineLogger) -> None:
        for candidate in candidates:
            report = self.fact_check_service.evaluate(candidate)
            self._attach_fact_check_report(candidate, report)
            if report.status == "verified":
                candidate.trend_score += 4.0
            elif report.status == "needs_review":
                candidate.trend_score -= 3.0
            elif report.status == "conflicting":
                candidate.trend_score -= 15.0
            elif report.status == "unsafe":
                candidate.trend_score -= 40.0
            logger.event(
                "fact_check_candidate",
                {
                    "title": candidate.title,
                    "country": candidate.country,
                    "status": report.status,
                    "summary": report.summary,
                },
            )

    def _attach_fact_check_report(self, candidate: TopicCandidate, report: FactCheckReport) -> None:
        candidate.fact_check_status = report.status
        candidate.extra["fact_check_report"] = to_dict(report)

    def _generate_country_assets(
        self,
        run_date: str,
        country_dir: Path,
        selected: SelectedTopic,
        logger: PipelineLogger,
    ) -> CountryRunArtifacts:
        provider = None
        script = None
        seo = None
        thumbnail = None
        last_error: Exception | None = None
        for candidate_provider in self.content_service.ordered_providers(
            self.config.content_provider.primary,
            self.config.content_provider.fallback,
        ):
            try:
                script = candidate_provider.generate_script(selected)
                seo = candidate_provider.generate_seo(selected, script)
                thumbnail = candidate_provider.generate_thumbnail(selected, script, seo)
                provider = candidate_provider
                break
            except Exception as exc:
                last_error = exc
                logger.warning(f"Content provider {candidate_provider.name} failed for {selected.candidate.country}: {exc}")
                continue

        if provider is None or script is None or seo is None or thumbnail is None:
            raise RuntimeError(f"All content providers failed for {selected.candidate.country}: {last_error}")

        scene_image_paths = self.scene_image_service.generate_scene_images(selected, script, country_dir)
        if scene_image_paths:
            thumbnail.source_image_path = str(scene_image_paths[0])
        thumbnail = self.thumbnail_renderer.render(thumbnail, country_dir, selected.language)

        subtitles_path = country_dir / "captions.srt"
        self._write_subtitles(subtitles_path, script)
        voiceover_path = None
        if self.config.global_defaults.enable_voiceover:
            voiceover_path = self._generate_voiceover(country_dir, selected, script, logger)

        write_json(country_dir / "topic.json", to_dict(selected.candidate))
        write_json(
            country_dir / "fact_check_report.json",
            selected.candidate.extra.get(
                "fact_check_report",
                {"status": selected.candidate.fact_check_status, "summary": "No fact-check report stored."},
            ),
        )
        write_json(
            country_dir / "research.json",
            {
                "topic": selected.candidate.title,
                "country": selected.candidate.country,
                "citations": selected.candidate.citations,
                "why_trending": selected.candidate.why_trending,
                "sources": [to_dict(source) for source in selected.candidate.sources],
                "risk_flags": selected.candidate.risk_flags,
                "fact_check_status": selected.candidate.fact_check_status,
                "fact_check_report": selected.candidate.extra.get("fact_check_report"),
            },
        )
        write_text(country_dir / "script.txt", self._script_to_text(script))
        write_text(country_dir / "title_options.txt", "\n".join(seo.title_options))
        write_text(country_dir / "final_title.txt", seo.final_title)
        write_text(country_dir / "description.txt", seo.description)
        write_text(country_dir / "hashtags.txt", "\n".join(seo.hashtags))
        write_text(country_dir / "thumbnail_prompt.txt", thumbnail.prompt)

        upload_payloads = {
            "youtube": self._build_upload_payload("youtube", selected, seo),
            "tiktok": self._build_upload_payload("tiktok", selected, seo),
            "instagram": self._build_upload_payload("instagram", selected, seo),
        }
        for platform, payload in upload_payloads.items():
            write_json(country_dir / f"upload_payload_{platform}.json", payload)

        metadata = {
            "run_date": run_date,
            "provider": provider.name,
            "topic": to_dict(selected),
            "script": to_dict(script),
            "seo": to_dict(seo),
            "thumbnail": to_dict(thumbnail),
            "scene_image_paths": [str(path) for path in scene_image_paths],
            "voiceover_path": str(voiceover_path) if voiceover_path else None,
            "fact_check_report": selected.candidate.extra.get("fact_check_report"),
            "performance_placeholders": {
                "platform": None,
                "upload_date": None,
                "views": None,
                "likes": None,
                "comments": None,
                "watch_time": None,
                "ctr": None,
                "retention": None,
            },
            "status": "prepared",
        }
        metadata_path = country_dir / "metadata.json"
        write_json(metadata_path, metadata)
        self.storage.record_artifact(
            run_date=run_date,
            country=selected.candidate.country,
            topic_title=selected.candidate.title,
            metadata=metadata,
            final_video_path=None,
            status="prepared",
        )
        logger.info(f"Prepared assets for {selected.candidate.country}: {selected.candidate.title}")
        return CountryRunArtifacts(
            selected_topic=selected,
            script=script,
            seo=seo,
            thumbnail=thumbnail,
            scene_image_paths=scene_image_paths,
            subtitles_path=subtitles_path,
            metadata_path=metadata_path,
            voiceover_path=voiceover_path,
            final_video_path=country_dir / "final_video.mp4",
        )

    def _render_country_video(
        self,
        run_date: str,
        artifact: CountryRunArtifacts,
        country_dir: Path,
        logger: PipelineLogger,
    ) -> None:
        request = VideoRenderRequest(
            country=artifact.selected_topic.candidate.country,
            run_date=run_date,
            output_dir=country_dir,
            topic=artifact.selected_topic,
            script=artifact.script,
            seo=artifact.seo,
            thumbnail=artifact.thumbnail,
            scene_image_paths=[str(path) for path in artifact.scene_image_paths],
            subtitles_path=artifact.subtitles_path,
            final_output_path=country_dir / "final_video.mp4",
            include_music=self.config.global_defaults.enable_background_music,
            include_voiceover=self.config.global_defaults.enable_voiceover,
            brand_intro=self.config.global_defaults.brand_intro,
            brand_outro=self.config.global_defaults.brand_outro,
            voiceover_audio_path=artifact.voiceover_path,
            background_music_path=None,
        )
        result = self.video_service.render(
            preferred=self.config.video_provider.primary,
            fallbacks=self.config.video_provider.fallback,
            request=request,
        )
        metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
        metadata["video"] = to_dict(result)
        metadata["status"] = "rendered"
        write_json(artifact.metadata_path, metadata)
        self.storage.record_artifact(
            run_date=run_date,
            country=artifact.selected_topic.candidate.country,
            topic_title=artifact.selected_topic.candidate.title,
            metadata=metadata,
            final_video_path=result.output_path,
            status=result.status,
        )
        logger.info(f"Rendered {artifact.selected_topic.candidate.country} video using {result.provider_name}")

    def _generate_voiceover(
        self,
        country_dir: Path,
        selected: SelectedTopic,
        script: ScriptPackage,
        logger: PipelineLogger,
    ) -> Path | None:
        script_path = country_dir / "voiceover_script.txt"
        write_text(script_path, script.voiceover_script)
        for provider in self.voice_service.ordered_providers():
            if provider.name == "noop":
                logger.warning(f"No voice provider available for {selected.candidate.country}; rendering without voiceover")
                return None
            suffix = ".aiff" if provider.name == "macos_say" else ".wav"
            output_path = country_dir / f"voiceover{suffix}"
            try:
                provider.synthesize(text=script.voiceover_script, language=selected.language, output_path=output_path)
                if not output_path.exists() or output_path.stat().st_size <= 4096:
                    raise RuntimeError("Voice file was created but contains no usable audio data.")
                logger.info(f"Generated voiceover for {selected.candidate.country} using {provider.name}")
                return output_path
            except Exception as exc:
                logger.warning(f"Voice provider {provider.name} failed for {selected.candidate.country}: {exc}")
                continue
        return None

    def _write_subtitles(self, path: Path, script: ScriptPackage) -> None:
        cursor = 0.0
        blocks = []
        for index, scene in enumerate(script.scenes, start=1):
            start = self._format_srt_timestamp(cursor)
            cursor += scene.duration_seconds
            end = self._format_srt_timestamp(cursor)
            blocks.append(f"{index}\n{start} --> {end}\n{scene.caption}\n")
        write_text(path, "\n".join(blocks))

    def _format_srt_timestamp(self, total_seconds: float) -> str:
        millis = int((total_seconds - int(total_seconds)) * 1000)
        total = int(total_seconds)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    def _script_to_text(self, script: ScriptPackage) -> str:
        lines = [f"Hook: {script.hook}", "", f"Summary: {script.summary}", ""]
        for scene in script.scenes:
            lines.extend(
                [
                    f"Scene {scene.index}: {scene.title}",
                    f"Visual: {scene.visual_prompt}",
                    f"Narration: {scene.narration}",
                    f"Caption: {scene.caption}",
                    f"Duration: {scene.duration_seconds}s",
                    "",
                ]
            )
        lines.append(f"CTA: {script.cta}")
        return "\n".join(lines)

    def _build_upload_payload(self, platform: str, selected: SelectedTopic, seo: SeoPackage) -> dict[str, Any]:
        tags_map = {
            "youtube": seo.youtube_tags,
            "tiktok": seo.tiktok_tags,
            "instagram": seo.instagram_tags,
        }
        return {
            "platform": platform,
            "title": seo.final_title,
            "description": seo.description,
            "hashtags": seo.hashtags,
            "keywords": seo.keywords,
            "filename": seo.upload_filename + ".mp4",
            "tags": tags_map[platform],
            "country": selected.candidate.country,
            "language": selected.language,
            "upload_enabled": False,
        }

    def _write_review_packet(self, output_dir: Path, artifacts: dict[str, CountryRunArtifacts]) -> Path:
        payload = {"run_date": output_dir.name, "countries": {}}
        blocks = []
        for country_name, artifact in artifacts.items():
            payload["countries"][country_name] = {
                "selected_topic": to_dict(artifact.selected_topic),
                "script": to_dict(artifact.script),
                "seo": to_dict(artifact.seo),
                "thumbnail": to_dict(artifact.thumbnail),
            }
            blocks.append(
                "<div class='card'>"
                f"<h2>{country_name.title()}</h2>"
                f"<p class='meta'>Topic: {artifact.selected_topic.candidate.title}</p>"
                f"<p><strong>Recommended title:</strong> {artifact.seo.final_title}</p>"
                f"<p><strong>Hook:</strong> {artifact.script.hook}</p>"
                f"<pre>{self._script_to_text(artifact.script)}</pre>"
                f"<img src='{Path(artifact.thumbnail.thumbnail_path).name}' alt='thumbnail' />"
                "</div>"
            )
        review_path = output_dir / "review_packet.json"
        write_json(review_path, payload)
        template_path = self.project_root / "templates" / "review.html.j2"
        html = template_path.read_text(encoding="utf-8")
        html = html.replace("{{RUN_DATE}}", output_dir.name).replace("{{COUNTRY_BLOCKS}}", "\n".join(blocks))
        write_text(output_dir / "review.html", html)
        return review_path

    def _load_artifact_from_disk(self, country_dir: Path, payload: dict[str, Any]) -> CountryRunArtifacts:
        candidate_payload = dict(payload["selected_topic"]["candidate"])
        candidate_payload["sources"] = [TopicSource(**source) for source in candidate_payload["sources"]]
        candidate = TopicCandidate(**candidate_payload)
        selected = SelectedTopic(
            candidate=candidate,
            language=payload["selected_topic"]["language"],
            tone=payload["selected_topic"]["tone"],
            duration_seconds=payload["selected_topic"]["duration_seconds"],
        )
        script = ScriptPackage(
            hook=payload["script"]["hook"],
            summary=payload["script"]["summary"],
            scenes=[Scene(**scene) for scene in payload["script"]["scenes"]],
            voiceover_script=payload["script"]["voiceover_script"],
            captions=payload["script"]["captions"],
            cta=payload["script"]["cta"],
            language=payload["script"]["language"],
            tone=payload["script"]["tone"],
        )
        seo = SeoPackage(**payload["seo"])
        thumbnail = ThumbnailPackage(**payload["thumbnail"])
        return CountryRunArtifacts(
            selected_topic=selected,
            script=script,
            seo=seo,
            thumbnail=thumbnail,
            scene_image_paths=[path for path in (country_dir / "scene_images").glob("*.png")] if (country_dir / "scene_images").exists() else [],
            subtitles_path=country_dir / "captions.srt",
            metadata_path=country_dir / "metadata.json",
            voiceover_path=(
                country_dir / "voiceover.wav"
                if (country_dir / "voiceover.wav").exists()
                else (country_dir / "voiceover.aiff" if (country_dir / "voiceover.aiff").exists() else None)
            ),
            final_video_path=country_dir / "final_video.mp4",
        )
