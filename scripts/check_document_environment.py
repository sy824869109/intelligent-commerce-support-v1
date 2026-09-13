"""Real offline synthetic PDF/table/Chinese OCR checks, not knowledge-ingestion business."""

from datetime import UTC, datetime
from io import BytesIO
import json
import logging
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "_local_artifacts/models/docling"


def native_pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    commands = ["BT /F1 22 Tf 50 740 Td (Environment sample) Tj ET"]
    for y, left, right in [
        (650, "Item", "Quantity"),
        (590, "Headphones", "2"),
        (530, "Cable", "1"),
    ]:
        for x, text in [(60, left), (330, right)]:
            commands.append(f"BT /F1 18 Tf {x} {y} Td ({text}) Tj ET")
    for y in (680, 620, 560, 500):
        commands.append(f"50 {y} m 500 {y} l S")
    for x in (50, 310, 500):
        commands.append(f"{x} 500 m {x} 680 l S")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output


def verify():
    from prepare_local_models import digest, safe_target
    from prepare_document_models import LOCK

    record = json.loads(LOCK.read_text(encoding="utf-8"))
    for entry in record["files"]:
        path = safe_target(BASE, entry["path"])
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise ValueError("Document asset changed")
    from docling.datamodel.base_models import InputFormat, DocumentStream
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from pypdf import PdfReader
    from PIL import Image, ImageDraw, ImageFont

    source = native_pdf()
    if "Headphones" not in PdfReader(source).pages[0].extract_text():
        raise ValueError("Native PDF reader failed")
    source.seek(0)
    options = PdfPipelineOptions(
        artifacts_path=BASE, do_ocr=True, do_table_structure=True, enable_remote_services=False
    )
    options.ocr_options = RapidOcrOptions(backend="torch", lang=["zh"])
    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    converted = converter.convert(DocumentStream(name="synthetic-table.pdf", stream=source))
    if (
        converted.status.value != "success"
        or "Headphones" not in converted.document.export_to_markdown()
        or not converted.document.tables
    ):
        raise ValueError("PDF/table pipeline failed")
    # Generated test fixture only; reading an existing Windows font does not install anything.
    picture = Image.new("RGB", (1500, 900), "white")
    draw = ImageDraw.Draw(picture)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 52)
    for y, text in [(130, "环境测试"), (240, "订单编号 TEST1001"), (350, "退货期限七天")]:
        draw.text((100, y), text, font=font, fill="black")
    scanned = BytesIO()
    picture.save(scanned, format="PDF", resolution=150)
    scanned.seek(0)
    ocr = converter.convert(DocumentStream(name="synthetic-scanned.pdf", stream=scanned))
    output = ocr.document.export_to_markdown()
    if ocr.status.value != "success" or "TEST1001" not in output or "退货" not in output:
        raise ValueError("Chinese scanned PDF OCR failed")
    return {
        "pypdf": "PASS",
        "docling_pdf": "PASS",
        "table_structure": "PASS",
        "chinese_scanned_ocr": "PASS",
        "inference_network": "offline",
        "customer_documents": "NONE",
    }


def main():
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "LANGSMITH_TRACING": "false",
            "DOCLING_CACHE_DIR": str(ROOT / "_local_artifacts/caches/docling"),
        }
    )
    logging.disable(logging.CRITICAL)
    result = {"checked_at": datetime.now(UTC).isoformat()}
    try:
        result.update(status="PASS", checks=verify())
    except Exception as error:
        import traceback

        result.update(
            status="FAILED",
            error_type=type(error).__name__,
            frames=[
                {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                for f in traceback.extract_tb(error.__traceback__)
            ],
        )
    path = ROOT / "_local_artifacts/environment/check-documents.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
