"""Schema regression tests for new operation types."""
import pytest
from models.schemas import (
    TitleBlockFields,
    UpdateTitleBlockOp,
    ExportFileConfig,
    ExportFileOp,
    CheckDrawingOp,
    OperationGraph,
)


def test_title_block_roundtrip():
    op = UpdateTitleBlockOp(
        id="tb1",
        type="update_title_block",
        title_block=TitleBlockFields(revision="C", drawn_by="John"),
    )
    assert op.title_block.revision == "C"
    assert op.title_block.drawn_by == "John"
    assert op.title_block.checked_by is None


def test_title_block_custom_fields():
    fields = TitleBlockFields(custom={"Project": "Acme-001", "Sheet": "1 of 3"})
    assert fields.custom["Project"] == "Acme-001"
    assert fields.revision is None


def test_export_file_op_roundtrip():
    op = ExportFileOp(
        id="ef1",
        type="export_file",
        export_file=ExportFileConfig(
            format="PDF",
            filename_template="{title}_{revision}_{date}",
        ),
    )
    assert op.export_file.format == "PDF"
    assert op.export_file.output_path is None


def test_check_drawing_op():
    op = CheckDrawingOp(id="cd1", type="check_drawing")
    assert op.type == "check_drawing"


def test_operation_graph_with_new_ops():
    graph = OperationGraph(
        operations=[
            {"id": "tb1", "type": "update_title_block",
             "title_block": {"revision": "B", "drawn_by": "Alice"}},
            {"id": "cd1", "type": "check_drawing"},
        ]
    )
    assert len(graph.operations) == 2
    assert graph.schema_version == "0.2"
