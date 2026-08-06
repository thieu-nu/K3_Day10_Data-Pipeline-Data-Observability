"""Giao dien demo cho lab Day 10 - Data Pipeline & Data Observability.

Moi con so hien tren man hinh deu doc tu artifact ma pipeline that su da ghi trong `data/`.
Khong tinh lai de hien thi va khong bia: artifact thieu thi bao thieu, metric null thi hien
N/A chu khong doi thanh 0.

    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

import pandas as pd
import streamlit as st

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.config import Settings, load_settings, normalized_provider  # noqa: E402
from observability.quality import freshness_report_path, quality_report_path  # noqa: E402

STATES = ("baseline", "corrupted", "repaired")
STATE_COLOUR = {"baseline": "#2563eb", "corrupted": "#dc2626", "repaired": "#16a34a"}

st.set_page_config(page_title="Day 10 - Data Pipeline & Observability", page_icon="🔎", layout="wide")


# --- doc artifact ------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _read_json(path_str: str, mtime: float) -> Any:
    del mtime  # nam trong cache key de file doi tren dia thi cache tu het han
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_json(path: Path | None) -> Any | None:
    if path is None or not Path(path).is_file():
        return None
    path = Path(path)
    return _read_json(str(path), path.stat().st_mtime)


def load_text(path: Path | None) -> str | None:
    if path is None or not Path(path).is_file():
        return None
    return Path(path).read_text(encoding="utf-8")


@st.cache_resource(show_spinner=False)
def get_settings() -> Settings:
    return load_settings()


def state_paths(settings: Settings) -> dict[str, dict[str, Path]]:
    p = settings.paths
    return {
        "baseline": {
            "metrics": p.baseline_metrics,
            "answers": p.baseline_answers,
            "quality": quality_report_path(settings, "baseline_quality"),
            # phase 1 ghi freshness cua baseline vao path dung chung trong config
            "freshness": p.freshness_report,
            "dataset": p.clean_csv,
            "embeddings": p.embeddings_json,
        },
        "corrupted": {
            "metrics": p.corrupted_metrics,
            "answers": p.corrupted_answers,
            "quality": quality_report_path(settings, "corrupted_quality"),
            "freshness": freshness_report_path(settings, "corrupted_freshness"),
            "dataset": p.corrupted_clean_csv,
            "embeddings": p.corrupted_embeddings_json,
        },
        "repaired": {
            "metrics": p.repaired_metrics,
            "answers": p.repaired_answers,
            "quality": quality_report_path(settings, "repaired_quality"),
            "freshness": freshness_report_path(settings, "repaired_freshness"),
            "dataset": p.repaired_clean_csv,
            "embeddings": p.repaired_embeddings_json,
        },
    }


# --- dinh dang ----------------------------------------------------------------------------


def fmt(value: Any, digits: int = 4) -> str:
    """Metric null hien N/A. Mot phep do khong co khong bao gio duoc hien thanh 0."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "có" if value else "không"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def fmt_delta(new: Any, old: Any, digits: int = 4) -> str | None:
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return None
    if isinstance(new, bool) or isinstance(old, bool):
        return None
    return f"{float(new) - float(old):+.{digits}f}"


def artifact_detail(path: Path) -> str:
    """Mo ta mot artifact bang chinh noi dung tren dia, khong doan."""
    path = Path(path)
    if not path.is_file():
        return "chưa có"
    size_kb = path.stat().st_size / 1024
    try:
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return f"{len(payload)} bản ghi · {size_kb:,.0f} KB"
            if isinstance(payload, dict):
                for key in ("row_count", "dataset_rows", "samples", "questions", "output_rows"):
                    if key in payload:
                        return f"{key}={payload[key]} · {size_kb:,.0f} KB"
                return f"{len(payload)} trường · {size_kb:,.0f} KB"
        if path.suffix == ".csv":
            rows = sum(1 for _ in path.open(encoding="utf-8")) - 1
            return f"{rows} dòng · {size_kb:,.0f} KB"
    except Exception as exc:
        return f"không đọc được: {type(exc).__name__}"
    return f"{size_kb:,.0f} KB"


def pipeline_stages(settings: Settings) -> pd.DataFrame:
    """Trang thai tung chang cua pipeline, doc tu file that tren dia."""
    p = settings.paths
    stages = [
        ("1. Raw ingest (Crossref)", p.raw_records_json),
        ("2. Cleaning", p.clean_csv),
        ("3. Clean contract gate", p.clean_gate_report),
        ("4. Embedding + Chroma index", p.embeddings_json),
        ("5. Evaluation set (đã khóa)", p.eval_testset),
        ("6. Evaluation baseline", p.baseline_metrics),
        ("7. Data quality baseline", quality_report_path(settings, "baseline_quality")),
        ("8. Freshness baseline", p.freshness_report),
        ("9. Báo cáo baseline", p.baseline_report),
        ("10. Corruption log", p.corruption_log),
        ("11. Evaluation corrupted", p.corrupted_metrics),
        ("12. Evaluation repaired", p.repaired_metrics),
        ("13. Báo cáo so sánh", p.comparison_report),
        ("14. Agent demo (LLM thật)", p.demo_answers),
    ]
    rows = []
    for label, path in stages:
        exists = Path(path).is_file()
        rows.append(
            {
                "": "🟢" if exists else "⚪",
                "Chặng": label,
                "Artifact": str(Path(path).relative_to(settings.paths.project_dir)),
                "Nội dung": artifact_detail(path),
                "Cập nhật": (
                    pd.Timestamp(Path(path).stat().st_mtime, unit="s", tz="UTC")
                    .tz_convert(None)
                    .strftime("%Y-%m-%d %H:%M")
                    if exists
                    else "—"
                ),
            }
        )
    return pd.DataFrame(rows)


def judge_scale_max(metrics: dict[str, Any] | None, default: float = 5.0) -> float:
    """Doc thang diem judge tu artifact thay vi gia dinh cung la 1-5."""
    scale = (metrics or {}).get("mean_judge_score_scale")
    if isinstance(scale, str) and "-" in scale:
        try:
            return float(scale.rsplit("-", 1)[1])
        except ValueError:
            pass
    return default


def kv_table(pairs: list[tuple[str, Any]], key_label: str = "Trường", value_label: str = "Giá trị"):
    """Bang key/value voi cot gia tri ep ve chuoi.

    Arrow khong suy duoc kieu cho mot cot tron str va int, nen bang key/value phai ep kieu;
    neu khong Streamlit van ve duoc nhung ban ghi mot ArrowTypeError moi lan render.
    """
    return pd.DataFrame(
        [(str(key), fmt(value)) for key, value in pairs], columns=[key_label, value_label]
    )


def status_badge(status: str | None) -> str:
    icons = {
        "pass": "🟢", "fresh": "🟢", "success": "🟢",
        "warning": "🟡", "partial": "🟡",
        "fail": "🔴", "stale": "🔴", "failed": "🔴",
        "unknown": "⚪", "unavailable": "⚪", "skipped": "⚪", "not_run": "⚪",
    }
    if status is None:
        return "⚪ N/A"
    return f"{icons.get(str(status), '⚪')} {status}"


def missing(what: str, how: str) -> None:
    st.warning(f"**Chưa có {what}.**\n\nChạy lệnh: `{how}`")


# --- cac tab -------------------------------------------------------------------------------


def page_overview(settings: Settings, metrics: dict[str, Any]) -> None:
    st.subheader("Trạng thái pipeline")
    stages = pipeline_stages(settings)
    done = int((stages[""] == "🟢").sum())
    st.progress(done / len(stages), text=f"{done}/{len(stages)} chặng đã sinh artifact")
    st.dataframe(stages, hide_index=True, width="stretch")
    st.caption(
        "Mỗi dòng đọc trực tiếp file trên đĩa: có tồn tại hay không, số bản ghi bên trong và "
        "thời điểm ghi. Không phải sơ đồ mô tả."
    )

    baseline = metrics.get("baseline")
    if baseline is None:
        missing("kết quả baseline", "python script/run_phase1.py")
        return

    st.subheader("Cấu hình lần chạy")
    left, right = st.columns(2)
    with left:
        st.dataframe(
            kv_table(
                [
                    ("LLM provider", baseline.get("provider")),
                    ("LLM model", baseline.get("model")),
                    ("Embedding model", baseline.get("embedding_model")),
                    ("top_k", baseline.get("top_k")),
                    ("Judge rubric", baseline.get("judge_rubric_version")),
                ],
                key_label="Cấu hình",
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption("Không đọc và không hiển thị API key ở đây, chỉ có tên provider và model.")
    with right:
        st.dataframe(
            kv_table(
                [
                    ("Evaluation set", baseline.get("evaluation_set_path")),
                    ("Số câu hỏi", baseline.get("samples")),
                    ("Số document đã index", baseline.get("index_document_count")),
                    ("Fingerprint", baseline.get("evaluation_set_fingerprint")),
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    fingerprints = {
        state: payload.get("evaluation_set_fingerprint")
        for state, payload in metrics.items()
        if payload
    }
    if len(set(fingerprints.values())) == 1 and len(fingerprints) > 1:
        st.success(
            f"Cả {len(fingerprints)} trạng thái đều được chấm trên cùng một evaluation set đã "
            f"khóa (`{next(iter(fingerprints.values()))[:16]}…`)."
        )
    elif len(fingerprints) > 1:
        st.error(
            "Các trạng thái được chấm trên những evaluation set khác nhau; delta không so sánh được."
        )

    st.subheader("Chỉ số chính")
    for state in STATES:
        payload = metrics.get(state)
        st.markdown(f"**{state}**")
        if payload is None:
            st.caption("chưa chạy")
            continue
        cols = st.columns(5)
        base = metrics.get("baseline") if state != "baseline" else None
        for col, (label, key) in zip(
            cols,
            [
                ("retrieval_hit_rate", "retrieval_hit_rate"),
                ("semantic_retrieval_hit_rate", "semantic_retrieval_hit_rate"),
                ("mean_token_f1", "mean_token_f1"),
                ("judge_accuracy", "judge_accuracy"),
                ("mean_judge_score (1-5)", "mean_judge_score"),
            ],
        ):
            delta = fmt_delta(payload.get(key), base.get(key)) if base else None
            col.metric(label, fmt(payload.get(key)), delta)


def page_comparison(metrics: dict[str, Any], quality: dict[str, Any], freshness: dict[str, Any]) -> None:
    baseline, corrupted = metrics.get("baseline"), metrics.get("corrupted")
    if baseline is None or corrupted is None:
        missing(
            "bảng so sánh",
            "python script/run_phase1.py && python script/run_corruption_flow.py",
        )
        return
    repaired = metrics.get("repaired")

    numeric = [
        "retrieval_hit_rate",
        "semantic_retrieval_hit_rate",
        "exact_lookup_success_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
    ]
    rows = []
    for key in numeric:
        rows.append(
            {
                "Metric / tín hiệu": key,
                "Baseline": fmt(baseline.get(key)),
                "Corrupted": fmt(corrupted.get(key)),
                "Repaired": fmt(repaired.get(key)) if repaired else "Chưa có",
                "Δ do corruption": fmt_delta(corrupted.get(key), baseline.get(key)) or "N/A",
                "Δ phục hồi": (
                    (fmt_delta(repaired.get(key), corrupted.get(key)) or "N/A") if repaired else "Chưa có"
                ),
            }
        )

    def read_status(source: dict[str, Any], state: str, key: str) -> Any:
        payload = source.get(state)
        if payload is None:
            return None
        return payload.get("summary", {}).get(key) if key == "overall_status" else payload.get(key)

    for label, source, key in (
        ("quality status", quality, "overall_status"),
        ("freshness status", freshness, "status"),
    ):
        rows.append(
            {
                "Metric / tín hiệu": label,
                "Baseline": fmt(read_status(source, "baseline", key)),
                "Corrupted": fmt(read_status(source, "corrupted", key)),
                "Repaired": fmt(read_status(source, "repaired", key)) if repaired else "Chưa có",
                "Δ do corruption": "—",
                "Δ phục hồi": "—",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        "Δ do corruption = `corrupted − baseline`; Δ phục hồi = `repaired − corrupted`. "
        "Metric null giữ nguyên N/A, không bao giờ bị coi là 0. Giá trị dạng status không có "
        "delta số."
    )

    chart_rows = []
    for key in numeric:
        # thang judge doc tu artifact, khong gia dinh cung la 1-5
        scale = judge_scale_max(baseline) if key == "mean_judge_score" else 1.0
        for state in STATES:
            payload = metrics.get(state)
            value = payload.get(key) if payload else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                chart_rows.append({"metric": key, "state": state, "value": value / scale})
    if chart_rows:
        st.subheader("So sánh đã chuẩn hóa")
        st.caption(
            "Mọi metric đưa về thang 0–1 để dùng chung trục; mean_judge_score chia cho "
            f"{judge_scale_max(baseline):.0f} (thang `{baseline.get('mean_judge_score_scale')}` "
            "đọc từ artifact)."
        )
        pivot = pd.DataFrame(chart_rows).pivot(index="metric", columns="state", values="value")
        # stack=False: ba trạng thái là các lựa chọn thay thế nhau, không phải thành phần của
        # một tổng. Bar chart xếp chồng sẽ khiến người xem tưởng chúng cộng lại có ý nghĩa.
        st.bar_chart(
            pivot,
            color=[STATE_COLOUR[c] for c in pivot.columns],
            height=340,
            stack=False,
        )

    base_n, corrupt_n = baseline.get("semantic_samples"), corrupted.get("semantic_samples")
    if base_n != corrupt_n:
        st.warning(
            f"Mẫu số của `semantic_retrieval_hit_rate` khác nhau (baseline n={base_n}, "
            f"corrupted n={corrupt_n}). Những câu hỏi có title trong nháy đơn không còn resolve "
            "được đã chuyển sang route semantic, nên dòng đó **không phải** so sánh tương đương. "
            "Phần `semantic_topic` bên dưới mới giữ mẫu số cố định."
        )

    st.subheader("Retrieval route")
    st.caption(
        "Câu hỏi có trích dẫn title có thể được trả lời bằng exact lookup trong `retrieval.qa`, "
        "bỏ qua vector search. Hai đường này được đếm tách biệt để thay đổi ở đường này không bị "
        "đọc nhầm thành thay đổi ở đường kia."
    )
    route_rows = []
    for state in STATES:
        payload = metrics.get(state)
        if payload is None:
            continue
        route_rows.append(
            {
                "Trạng thái": state,
                "exact_lookup samples": fmt(payload.get("exact_lookup_samples")),
                "exact_lookup_success_rate": fmt(payload.get("exact_lookup_success_rate")),
                "semantic samples": fmt(payload.get("semantic_samples")),
                "semantic_retrieval_hit_rate": fmt(payload.get("semantic_retrieval_hit_rate")),
            }
        )
    st.dataframe(pd.DataFrame(route_rows), hide_index=True, width="stretch")


def page_quality(quality: dict[str, Any], freshness: dict[str, Any]) -> None:
    if not any(quality.values()):
        missing("quality report", "python script/run_phase1.py")
        return

    st.subheader("Freshness")
    cols = st.columns(3)
    for col, state in zip(cols, STATES):
        payload = freshness.get(state)
        with col:
            st.markdown(f"**{state}**")
            if payload is None:
                st.caption("chưa chạy")
                continue
            st.markdown(f"### {status_badge(payload.get('status'))}")
            st.caption(payload.get("reason", ""))
            st.dataframe(
                kv_table(
                    [
                        ("Số dòng", payload.get("row_count")),
                        ("Threshold (ngày)", payload.get("threshold_days")),
                        ("Số dòng stale", payload.get("stale_rows")),
                        ("max age_days", payload.get("max_age_days")),
                        ("published cũ nhất", payload.get("oldest_published")),
                        ("Dòng không có ngày hợp lệ", payload.get("invalid_or_missing_date_rows")),
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

    st.subheader("Data quality checks")
    state = st.radio("Trạng thái", [s for s in STATES if quality.get(s)], horizontal=True)
    payload = quality[state]
    summary = payload.get("summary", {})
    cols = st.columns(4)
    cols[0].metric("Tổng kết", summary.get("overall_status", "N/A"))
    cols[1].metric("Pass", summary.get("passed"))
    cols[2].metric("Warning", summary.get("warned"))
    cols[3].metric("Fail", summary.get("failed"))

    checks = pd.DataFrame(payload.get("checks", []))
    if not checks.empty:
        if st.checkbox("Chỉ hiện check không pass", value=False):
            checks = checks[checks["status"] != "pass"]
        checks = checks[
            [
                "check_name",
                "quality_dimension",
                "status",
                "observed_value",
                "expected_condition",
                "affected_count",
                "total_count",
                "message",
            ]
        ].rename(
            columns={
                "affected_count": "số dòng lỗi",
                "total_count": "tổng số dòng",
                "message": "mô tả",
            }
        )
        st.dataframe(checks.astype(str), hide_index=True, width="stretch")


def page_questions(metrics: dict[str, Any], answers: dict[str, Any]) -> None:
    baseline = answers.get("baseline")
    if not baseline:
        missing("kết quả evaluation", "python script/run_phase1.py")
        return

    by_state = {state: {row["id"]: row for row in (answers.get(state) or [])} for state in STATES}
    rows = []
    for item in baseline:
        sample_id = item["id"]
        row = {"id": sample_id, "question_type": item["question_type"], "Câu hỏi": item["question"]}
        for state in STATES:
            other = by_state[state].get(sample_id)
            row[f"{state} hit"] = other.get("retrieval_hit") if other else None
            row[f"{state} F1"] = other.get("token_f1") if other else None
        rows.append(row)
    table = pd.DataFrame(rows)

    degraded = []
    corrupted_map = by_state["corrupted"]
    for item in baseline:
        after = corrupted_map.get(item["id"])
        if not after:
            continue
        lost_hit = item.get("retrieval_hit") and not after.get("retrieval_hit")
        f1_drop = (
            isinstance(item.get("token_f1"), (int, float))
            and isinstance(after.get("token_f1"), (int, float))
            and after["token_f1"] < item["token_f1"]
        )
        route_lost = (
            item.get("evaluation_route") == "exact_lookup"
            and after.get("evaluation_route") == "semantic_search"
        )
        if lost_hit or f1_drop or route_lost:
            degraded.append(item["id"])

    if corrupted_map:
        if degraded:
            st.error(f"{len(degraded)}/{len(baseline)} câu hỏi bị kém đi sau corruption.")
        else:
            st.info(
                "Không có câu hỏi nào kém đi sau corruption trên evaluation set hiện tại. Đây là "
                "kết quả đo được, không suy diễn thêm: nhiều khả năng corruption không chạm vào "
                "các document mà những câu hỏi này trỏ tới."
            )

    show_only = (
        st.checkbox("Chỉ hiện câu bị kém đi", value=bool(degraded)) if degraded else False
    )
    st.dataframe(
        table[table["id"].isin(degraded)] if show_only else table, hide_index=True, width="stretch"
    )

    st.subheader("Chi tiết từng câu")
    sample_id = st.selectbox("Chọn câu hỏi", table["id"].tolist())
    available = [s for s in STATES if by_state[s]]
    for col, state in zip(st.columns(len(available)), available):
        item = by_state[state].get(sample_id)
        with col:
            st.markdown(f"**{state}**")
            if item is None:
                st.caption("chưa evaluate")
                continue
            if item.get("status") != "evaluated":
                st.error(f"thất bại: {item.get('error')}")
                continue
            st.markdown(f"Route `{item.get('evaluation_route')}` · hit rank {fmt(item.get('hit_rank'))}")
            st.metric("token_f1", fmt(item.get("token_f1")))
            verdict = item.get("judge")
            if verdict:
                st.metric("judge score", f"{verdict['score']}/5")
                st.caption(verdict.get("reasoning", ""))
            else:
                st.caption(f"judge {status_badge(item.get('judge_status'))}")
                if item.get("judge_error"):
                    st.caption(f"`{item['judge_error'][:160]}`")
            st.markdown("**Câu trả lời**")
            st.write(item.get("answer") or "_(rỗng)_")
            st.markdown("**Document được retrieve**")
            for rank, doc_id in enumerate(item.get("retrieved_doc_ids", []), start=1):
                marker = "✅" if doc_id in item.get("ground_truth_doc_ids", []) else "▫️"
                st.caption(f"{marker} {rank}. `{doc_id}`")

    first = by_state["baseline"].get(sample_id)
    if first:
        st.markdown("**Ground truth**")
        st.info(first.get("ground_truth"))


def page_corruption_log(settings: Settings) -> None:
    log = load_json(settings.paths.corruption_log)
    if log is None:
        missing("corruption log", "python script/run_corruption_flow.py")
        return

    cols = st.columns(4)
    cols[0].metric("Dòng đầu vào", log.get("input_rows"))
    cols[1].metric("Dòng đầu ra", log.get("output_rows"))
    cols[2].metric("Đã xóa", log.get("rows_removed"))
    cols[3].metric("Đã thêm", log.get("rows_added"))
    st.caption(
        f"Kết quả tất định với seed `{log.get('seed')}`, sinh lúc {log.get('generated_at')}."
    )

    counts = log.get("scenario_counts", {})
    if counts:
        st.subheader("Các kịch bản corruption")
        st.bar_chart(pd.Series(counts, name="số dòng bị ảnh hưởng"), height=260)

    events = log.get("events", [])
    if events:
        st.subheader("Toàn bộ record bị ảnh hưởng")
        st.dataframe(
            pd.DataFrame(events).rename(
                columns={
                    "corruption_type": "loại corruption",
                    "affected_field": "trường bị ảnh hưởng",
                    "detail": "chi tiết",
                }
            ),
            hide_index=True,
            width="stretch",
        )


def page_ask(settings: Settings) -> None:
    st.caption(
        "Chạy đúng đường retrieval mà evaluation dùng, trên index của trạng thái bạn chọn. "
        "Đổi sang index corrupted là cách nhanh nhất để thấy dữ liệu hỏng ảnh hưởng thế nào."
    )
    paths = state_paths(settings)
    available = [s for s in STATES if Path(paths[s]["embeddings"]).is_file()]
    if not available:
        missing("index nào", "python script/run_phase1.py")
        return

    state = st.radio("Index", available, horizontal=True)

    # Goi y lay tu chinh test set da khoa, khong phai chuoi viet cung
    suggestions = [""]
    test_set = load_json(settings.paths.eval_testset)
    if isinstance(test_set, list):
        suggestions += [item["question"] for item in test_set]
    picked = st.selectbox(
        "Chọn một câu từ evaluation set (hoặc để trống rồi tự gõ)",
        suggestions,
        format_func=lambda s: "— tự gõ —" if not s else s[:110],
    )
    question = st.text_input("Câu hỏi", value=picked)
    use_agent = st.checkbox(
        "Dùng LLM agent thật (`retrieval.agent`) thay vì đường retrieval của evaluation",
        value=False,
        help="Agent tự quyết định gọi tool semantic_search_papers hay lookup_paper. Tốn quota LLM.",
    )
    st.caption(
        "Đường retrieval của evaluation (`retrieval.qa`) định tuyến theo từ khóa: "
        "*Who authored…* / *When was… published* / *What categories…* đọc thẳng metadata; "
        "còn lại trả về câu đầu tiên trong summary của paper đứng đầu. "
        "Title trong 'nháy đơn' kích hoạt exact lookup. Agent thật thì không theo luật này."
    )
    if not question:
        return

    try:
        from retrieval.index import LocalEmbeddingIndex
        from retrieval.qa import answer_question

        with st.spinner("Đang tìm trong corpus đã index…"):
            index = LocalEmbeddingIndex.load(settings, Path(paths[state]["embeddings"]))
            result = answer_question(question, settings=settings, index=index)
    except Exception as exc:  # hiển thị lỗi, không nuốt
        st.error(f"Retrieval thất bại: {type(exc).__name__}: {exc}")
        return

    left, right = st.columns(2) if use_agent else (st.container(), None)
    with left:
        st.markdown("### `retrieval.qa` (đường evaluation chấm điểm)")
        st.success(result.answer or "_(rỗng)_")
        st.dataframe(
            pd.DataFrame(
                {
                    "rank": range(1, len(result.retrieved_doc_ids) + 1),
                    "paper_id": result.retrieved_doc_ids,
                    "title": result.retrieved_titles,
                }
            ),
            hide_index=True,
            width="stretch",
        )

    if use_agent and right is not None:
        with right:
            st.markdown("### `retrieval.agent` (LLM agent có tool)")
            try:
                from retrieval.agent import build_agent, run_agent_question

                with st.spinner("Agent đang suy luận và gọi tool…"):
                    agent = build_agent(settings=settings, index=index)
                    answer = run_agent_question(agent, question)
                st.success(answer or "_(rỗng)_")
            except Exception as exc:
                from evaluation.metrics import _sanitize_error

                st.error(
                    f"Agent thất bại: {type(exc).__name__}\n\n"
                    f"`{_sanitize_error(exc, settings)}`"
                )
                st.caption(
                    "Lỗi được hiển thị nguyên trạng đã che credential. Không có câu trả lời "
                    "thay thế nào được sinh ra."
                )

    with st.expander("Xem context đã retrieve"):
        for doc_id, context in zip(result.retrieved_doc_ids, result.retrieved_contexts):
            st.markdown(f"**`{doc_id}`**")
            st.caption(context[:700] + ("…" if len(context) > 700 else ""))


def page_agent(settings: Settings) -> None:
    st.caption(
        "Chạy LLM agent thật (`retrieval.agent`) trên chính các câu hỏi của evaluation set đã "
        "khóa, rồi chấm bằng đúng token F1 và đúng ground truth mà evaluation dùng. Nhờ vậy so "
        "sánh được agent với đường `retrieval.qa` theo luật từ khóa."
    )
    payload = load_json(settings.paths.demo_answers)

    paths = state_paths(settings)
    available = [s for s in STATES if Path(paths[s]["embeddings"]).is_file()]
    if not available:
        missing("index nào", "python script/run_phase1.py")
        return

    cols = st.columns([1, 1, 2])
    state = cols[0].selectbox("Index", available)
    count = cols[1].number_input("Số câu hỏi", min_value=1, max_value=12, value=4, step=1)
    cols[2].markdown("&nbsp;", unsafe_allow_html=True)
    if cols[2].button("▶ Chạy agent demo", type="primary"):
        from pipelines.agent_demo import run_agent_demo

        with st.spinner(f"Agent đang trả lời {count} câu trên index {state}…"):
            try:
                payload = run_agent_demo(settings, state=state, count=int(count))
                st.cache_data.clear()
            except Exception as exc:
                st.error(f"Không chạy được agent demo: {type(exc).__name__}: {exc}")
                return

    if payload is None:
        st.info(
            "Chưa có kết quả agent demo. Bấm nút ở trên, hoặc chạy "
            "`python script/run_agent_demo.py`."
        )
        return

    cols = st.columns(5)
    cols[0].metric("Số câu", payload.get("questions"))
    cols[1].metric("Trả lời được", payload.get("answered"))
    cols[2].metric("Thất bại", payload.get("failed"))
    cols[3].metric("Agent mean token F1", fmt(payload.get("mean_agent_token_f1")))
    cols[4].metric("retrieval.qa mean token F1", fmt(payload.get("mean_qa_token_f1")))

    if payload.get("mean_agent_token_f1") is None:
        st.warning(
            "Không có lời gọi agent nào thành công, nên `mean_agent_token_f1` là N/A. "
            "Không có điểm thay thế nào được sinh ra."
        )
    st.caption(
        f"State `{payload.get('state')}` · provider `{payload.get('provider')}` · model "
        f"`{payload.get('model')}` · chạy lúc {payload.get('completed_at')}"
    )

    for item in payload.get("items", []):
        label = f"{item.get('question_type')} · {item.get('id')}"
        with st.expander(f"{'✅' if item.get('status') == 'answered' else '❌'} {label}"):
            st.markdown(f"**Câu hỏi:** {item.get('question')}")
            st.info(f"**Ground truth:** {item.get('ground_truth')}")
            left, right = st.columns(2)
            with left:
                st.markdown("**LLM agent**")
                if item.get("status") == "answered":
                    st.success(item.get("agent_answer") or "_(rỗng)_")
                    st.metric("token_f1", fmt(item.get("agent_token_f1")))
                    st.caption(
                        f"Tool đã gọi: {', '.join(item.get('tool_calls') or []) or 'không gọi tool nào'}"
                        f" · {item.get('message_count')} message · {item.get('duration_ms')} ms"
                    )
                else:
                    st.error(item.get("error"))
            with right:
                st.markdown("**`retrieval.qa`**")
                st.write(item.get("qa_answer") or "_(không có)_")
                st.metric("token_f1", fmt(item.get("qa_token_f1")))


def page_run(settings: Settings) -> None:
    import subprocess

    st.caption(
        "Chạy chính các entrypoint trong `script/`. Toàn bộ artifact trong `data/` sẽ được "
        "sinh lại từ dữ liệu thật; giao diện không tự bịa kết quả nào."
    )
    project = settings.paths.project_dir
    jobs = {
        "Baseline (run_phase1.py)": "script/run_phase1.py",
        "Corruption + repair (run_corruption_flow.py)": "script/run_corruption_flow.py",
        "Agent demo (run_agent_demo.py)": "script/run_agent_demo.py",
    }
    choice = st.radio("Chọn pipeline", list(jobs), index=0)
    st.code(f"{Path(sys.executable).name} {jobs[choice]}", language="bash")
    st.warning(
        "Baseline và corruption flow gọi LLM judge cho từng câu hỏi. Trên free tier của "
        "OpenRouter việc này rất dễ chạm hạn mức ngày; những lần gọi thất bại sẽ được ghi là "
        "failure chứ không được cho điểm."
    )

    if st.button(f"▶ Chạy {choice}", type="primary"):
        placeholder = st.empty()
        with st.spinner("Đang chạy… có thể mất vài phút"):
            completed = subprocess.run(
                [sys.executable, jobs[choice]],
                cwd=str(project),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        if completed.returncode == 0:
            placeholder.success(f"Hoàn tất (exit code {completed.returncode})")
        else:
            placeholder.error(f"Thất bại (exit code {completed.returncode})")
        output = (completed.stdout or "") + (completed.stderr or "")
        st.text_area("Output", output[-8000:], height=320)
        st.cache_data.clear()
        st.caption("Artifact đã được nạp lại; chuyển sang tab khác để xem số liệu mới.")


def page_reports(settings: Settings) -> None:
    for label, path, how in (
        ("Báo cáo baseline", settings.paths.baseline_report, "python script/run_phase1.py"),
        (
            "Báo cáo so sánh corruption",
            settings.paths.comparison_report,
            "python script/run_corruption_flow.py",
        ),
    ):
        st.subheader(label)
        text = load_text(path)
        if text is None:
            missing(label.lower(), how)
            continue
        st.caption(f"`{path}`")
        with st.expander("Xem báo cáo", expanded=False):
            st.markdown(text)
        st.download_button(
            f"Tải {Path(path).name}", text, file_name=Path(path).name, mime="text/markdown"
        )


# --- main -----------------------------------------------------------------------------------


def main() -> None:
    settings = get_settings()
    paths = state_paths(settings)

    metrics = {state: load_json(paths[state]["metrics"]) for state in STATES}
    answers = {state: load_json(paths[state]["answers"]) for state in STATES}
    quality = {state: load_json(paths[state]["quality"]) for state in STATES}
    freshness = {state: load_json(paths[state]["freshness"]) for state in STATES}

    st.title("🔎 Data Pipeline & Data Observability")
    st.caption(
        "Dữ liệu lỗi có thực sự làm RAG agent kém đi hay không, và sửa dữ liệu có kéo chất lượng "
        "trở lại không? Mọi con số bên dưới đều đọc từ artifact trong `data/`."
    )

    with st.sidebar:
        st.header("Trạng thái các lần chạy")
        for state in STATES:
            st.write(f"{'🟢' if metrics.get(state) else '⚪'} evaluation {state}")
        st.write(f"{'🟢' if load_json(settings.paths.eval_testset) else '⚪'} evaluation set")
        st.write(f"{'🟢' if load_json(settings.paths.corruption_log) else '⚪'} corruption log")
        st.divider()
        st.header("LLM provider")
        st.write(f"`{normalized_provider(settings)}`")
        st.write(f"`{settings.model_name}`")
        st.caption(
            "Đã có credential cho LLM judge."
            if settings.openrouter_api_key
            else "Chưa có credential: judge metrics sẽ được ghi là unavailable chứ không bịa số."
        )
        st.divider()
        st.caption("Sinh lại toàn bộ artifact:")
        st.code("python script/run_phase1.py\npython script/run_corruption_flow.py", language="bash")
        if st.button("Tải lại artifact"):
            st.cache_data.clear()
            st.rerun()

    tabs = st.tabs(
        [
            "Tổng quan",
            "So sánh",
            "Quality & freshness",
            "Câu hỏi",
            "Corruption log",
            "LLM agent",
            "Hỏi thử",
            "Chạy pipeline",
            "Báo cáo",
        ]
    )
    with tabs[0]:
        page_overview(settings, metrics)
    with tabs[1]:
        page_comparison(metrics, quality, freshness)
    with tabs[2]:
        page_quality(quality, freshness)
    with tabs[3]:
        page_questions(metrics, answers)
    with tabs[4]:
        page_corruption_log(settings)
    with tabs[5]:
        page_agent(settings)
    with tabs[6]:
        page_ask(settings)
    with tabs[7]:
        page_run(settings)
    with tabs[8]:
        page_reports(settings)


main()
