from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import settings


NAVY = colors.HexColor("#0B1F33")
GOLD = colors.HexColor("#C9A227")
SLATE = colors.HexColor("#E8EEF4")
MUTED = colors.HexColor("#5C7388")
LINE = colors.HexColor("#1E3A5F")
FLAG = colors.HexColor("#F4E4C1")
OK_ROW = colors.HexColor("#F4F7FA")


def report_paths(report_id: str) -> tuple[Path, Path]:
    root = Path(settings.report_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{report_id}.json", root / f"{report_id}.pdf"


def write_json_report(report_id: str, payload: dict) -> Path:
    json_path, _ = report_paths(report_id)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def _styles():
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "VSTitle",
        parent=base["Title"],
        fontName="Times-Bold",
        fontSize=18,
        textColor=NAVY,
        spaceAfter=6,
        alignment=1,
    )
    section = ParagraphStyle(
        "VSSection",
        parent=base["Heading2"],
        fontName="Times-Bold",
        fontSize=12,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "VSSub",
        parent=base["Normal"],
        fontSize=10,
        textColor=MUTED,
        spaceAfter=12,
        alignment=1,
    )
    body = ParagraphStyle(
        "VSBody",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        textColor=NAVY,
        spaceAfter=8,
    )
    small = ParagraphStyle("VSSmall", parent=body, fontSize=8, textColor=MUTED, leading=11)
    cell = ParagraphStyle("VSCell", parent=body, fontSize=8, leading=11, spaceAfter=0)
    return title, section, subtitle, body, small, cell


def _table(data: list[list], col_widths: list[float] | None = None, header: bool = True) -> Table:
    table = Table(data, colWidths=col_widths)
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), SLATE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, OK_ROW]),
            ]
        )
    else:
        commands.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, OK_ROW]))
    table.setStyle(TableStyle(commands))
    return table


def write_pdf_report(report_id: str, payload: dict) -> Path:
    _, pdf_path = report_paths(report_id)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"VeriSonar {report_id}",
        author="VeriSonar",
    )
    title, section, subtitle, body, small, cell = _styles()
    exam = payload.get("exam") or {}
    vsa = payload.get("vsa") or {}
    code = exam.get("evaluation_code") or report_id

    story = [
        Paragraph("VeriSonar", title),
        Paragraph("Acta de análisis de estrés de voz (VSA)", subtitle),
        Paragraph(f"Evaluación {escape(str(code))}", subtitle),
        Paragraph(payload.get("summary") or "", body),
    ]

    story.append(Paragraph("1. Datos del examen", section))
    ficha = [
        ["Campo", "Dato"],
        ["Número de evaluación", str(exam.get("evaluation_code") or "—")],
        ["Expediente", str(exam.get("title") or "—")],
        ["Evaluado", str(exam.get("subject_name") or "—")],
        ["Identificación", str(exam.get("subject_document") or "—")],
        ["Lugar", str(exam.get("location") or "—")],
        ["Modalidad", str(exam.get("modality") or "—")],
        ["Finalidad", str(exam.get("purpose") or exam.get("context") or "—")],
        ["Evaluador", str(exam.get("evaluator_name") or "—")],
        ["Cargo", str(exam.get("evaluator_title") or "—")],
        ["Idioma", str(payload.get("language") or exam.get("language") or "es")],
        ["Fecha", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
    ]
    story.append(_table(ficha, [6 * cm, 10 * cm]))

    story.append(Paragraph("2. Protocolo y línea base", section))
    protocol = [
        ["Métrica", "Valor"],
        ["Método", str(payload.get("method") or "vsa-control-baseline-v1")],
        ["Línea base (media de controles)", f"{vsa.get('baseline', 0):.2f}" if vsa else "n/d"],
        ["Índice VSA (ítems relevantes)", f"{vsa.get('vsa_index', 0):.2f}" if vsa else "n/d"],
        ["Controles / estímulos / relevantes", (
            f"{vsa.get('control_count', 0)} / {vsa.get('stimulus_count', 0)} / {vsa.get('relevant_count', 0)}"
            if vsa
            else "n/d"
        )],
        ["Ítems sobre la línea base", str(vsa.get("flagged_count", 0) if vsa else "n/d")],
        ["Índice de confiabilidad global", f"{payload.get('reliability_index', 0):.0%}"],
        ["Índice de riesgo global", f"{payload.get('deception_index', 0):.0%}"],
        ["Banda de riesgo", str(payload.get("risk_band") or "")],
        ["Motor STT", str(payload.get("stt_engine") or "n/d")],
        ["Motor acústico", str(payload.get("acoustic_engine") or "librosa")],
    ]
    aco = payload.get("acoustic_features") or {}
    if aco.get("praat"):
        jitter = aco.get("jitter_local")
        shimmer = aco.get("shimmer_local")
        protocol.extend(
            [
                ["HNR (Praat)", f"{aco.get('hnr_mean_db')} dB" if aco.get("hnr_mean_db") is not None else "n/d"],
                ["Jitter local (Praat)", f"{jitter:.2%}" if isinstance(jitter, (int, float)) else "n/d"],
                ["Shimmer local (Praat)", f"{shimmer:.2%}" if isinstance(shimmer, (int, float)) else "n/d"],
                ["F0 medio", f"{aco.get('pitch_mean_hz')} Hz" if aco.get("pitch_mean_hz") is not None else "n/d"],
            ]
        )
    story.append(_table(protocol, [8 * cm, 8 * cm]))
    if vsa.get("note"):
        story.append(Paragraph(escape(str(vsa["note"])), small))

    story.append(Paragraph("3. Resultados por ítem", section))
    items = vsa.get("items") or []
    if items:
        header = [
            Paragraph("<b>#</b>", cell),
            Paragraph("<b>Tipo</b>", cell),
            Paragraph("<b>Pregunta</b>", cell),
            Paragraph("<b>VSA</b>", cell),
            Paragraph("<b>Δ base</b>", cell),
            Paragraph("<b>Alerta</b>", cell),
        ]
        rows = [header]
        for item in items:
            question = escape(str(item.get("question") or "—"))
            if len(question) > 90:
                question = question[:87] + "…"
            rows.append(
                [
                    str(item.get("index") or ""),
                    str(item.get("kind_label") or item.get("kind") or ""),
                    Paragraph(question, cell),
                    f"{float(item.get('vsa_score') or 0):.2f}",
                    f"{float(item.get('delta') or 0):+.2f}",
                    "Sí" if item.get("flagged") else "No",
                ]
            )
        item_table = _table(rows, [1.2 * cm, 2.4 * cm, 7.2 * cm, 1.6 * cm, 1.8 * cm, 1.8 * cm])
        for index, item in enumerate(items, start=1):
            if item.get("flagged"):
                item_table.setStyle(TableStyle([("BACKGROUND", (0, index), (-1, index), FLAG)]))
        story.append(item_table)
    else:
        story.append(Paragraph("No hay clips pregunta/respuesta para puntuar contra la línea base.", body))

    findings = payload.get("findings") or []
    story.append(Paragraph("4. Hallazgos y transcripción", section))
    if not findings:
        story.append(Paragraph("No se registraron pistas por encima del umbral.", body))
    for item in findings:
        story.append(
            Paragraph(
                f"<b>{escape(str(item.get('title') or ''))}</b> ({escape(str(item.get('severity') or ''))}) — "
                f"{escape(str(item.get('detail') or ''))}"
                + (f" <i>Evidencia: {escape(str(item.get('evidence')))}</i>" if item.get("evidence") else ""),
                body,
            )
        )

    interview = payload.get("interview") or {}
    audio_id = payload.get("audio_id") or ""
    wave_png = Path(settings.upload_dir) / str(audio_id) / "waveform.png" if audio_id else None
    if wave_png and wave_png.exists():
        story.append(Paragraph("Forma de onda", section))
        story.append(Image(str(wave_png), width=16 * cm, height=4.8 * cm))
        story.append(Spacer(1, 10))

    story.append(Paragraph("Transcripción", section))
    transcript = payload.get("transcription") or "Sin transcripción disponible."
    story.append(Paragraph(escape(transcript).replace("\n", "<br/>"), body))

    exchanges = interview.get("exchanges") or []
    if exchanges:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Clips pregunta y respuesta", section))
        for clip in exchanges:
            kind = escape(str(clip.get("kind_label") or ""))
            score = clip.get("vsa_score")
            score_txt = f" · VSA {float(score):.2f}" if isinstance(score, (int, float)) else ""
            flag = " · sobre línea base" if clip.get("flagged") else ""
            block = [
                Paragraph(
                    f"<b>Clip {clip.get('index')}</b> {kind}{score_txt}{flag} "
                    f"({clip.get('start', 0):.1f}s – {clip.get('end', 0):.1f}s)",
                    body,
                ),
                Paragraph(f"<b>Interrogador:</b> {escape(str(clip.get('question') or '—'))}", body),
                Paragraph(f"<b>Interrogado:</b> {escape(str(clip.get('answer') or '—'))}", body),
            ]
            stem = f"{int(clip.get('index') or 0):02d}"
            clip_dir = Path(settings.upload_dir) / str(audio_id) / "clips"
            clip_png = clip_dir / f"{stem}.png"
            vsa_png = clip_dir / f"{stem}.vsa.png"
            comb_png = clip_dir / f"{stem}.comb.png"
            include_vsa = bool(clip.get("include_vsa_in_report", False))
            include_comb = bool(clip.get("include_comb_in_report", False))
            if clip_png.exists():
                block.append(Image(str(clip_png), width=16 * cm, height=3.2 * cm))
            if include_vsa and vsa_png.exists():
                block.append(Paragraph("Gráfica VSA de la respuesta", body))
                block.append(Image(str(vsa_png), width=16 * cm, height=3.2 * cm))
                vsa_note = str(clip.get("vsa_report_note") or "").strip()
                if vsa_note:
                    block.append(Paragraph(escape(vsa_note), small))
            if include_comb and comb_png.exists():
                block.append(Paragraph("Gráfica peine de la respuesta", body))
                block.append(Image(str(comb_png), width=16 * cm, height=3.2 * cm))
                comb_note = str(clip.get("comb_report_note") or "").strip()
                if comb_note:
                    block.append(Paragraph(escape(comb_note), small))
            story.append(KeepTogether(block + [Spacer(1, 8)]))

    story.append(Spacer(1, 10))
    story.append(Paragraph(payload.get("disclaimer") or "", small))
    doc.build(story)
    return pdf_path
