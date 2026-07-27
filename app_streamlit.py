from __future__ import annotations

from pathlib import Path
from typing import Any

import chess.svg
import cv2
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from chess_diagram_ocr.board_detection import detect_boards
from chess_diagram_ocr.config import (
    DEFAULT_DATASET_CSV,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_SAMPLES_DIR,
    find_default_pdf_path,
)
from chess_diagram_ocr.dataset import append_training_sample
from chess_diagram_ocr.detection import detect_diagrams_in_pdf_page
from chess_diagram_ocr.fen_utils import board_from_fen, check_position, is_valid_fen
from chess_diagram_ocr.inference import load_model, predict_with_orientation
from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page
from chess_diagram_ocr.pdf_text import DiagramContext, contexts_for_pdf_page
from chess_diagram_ocr.semantics import compose_fen, infer_side_to_move
from chess_diagram_ocr.training import train_model


@st.cache_resource(show_spinner=False)
def get_loaded_model(model_path_text: str):
    return load_model(Path(model_path_text))


@st.cache_data(show_spinner=False)
def render_pdf_page_cached(pdf_source: Any, page_index: int, dpi: int) -> np.ndarray:
    return render_pdf_page(pdf_source, page_index, dpi=dpi)


def _set_results(source_rgb: np.ndarray, items: list[dict[str, Any]], origin: str) -> None:
    _clear_results()
    st.session_state["result_source_rgb"] = source_rgb
    st.session_state["result_items"] = items
    st.session_state["result_origin"] = origin
    st.session_state["selected_result_idx"] = 0
    st.session_state["selected_result_one_based"] = 1
    st.session_state["fen_edits"] = [item["fen_pred"] for item in items]


def _clear_results() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(("fen_edit_", "side_edit_")):
            del st.session_state[key]
    for key in [
        "result_source_rgb",
        "result_items",
        "result_origin",
        "selected_result_idx",
        "selected_result_one_based",
        "fen_edits",
    ]:
        st.session_state.pop(key, None)


def run_ocr_for_boards(
    source_rgb: np.ndarray,
    boards_with_quads: list[tuple[np.ndarray, np.ndarray | None]],
    model_path: Path,
    orientation: str,
    origin: str,
    contexts: list[DiagramContext] | None = None,
) -> None:
    if not boards_with_quads:
        _clear_results()
        raise ValueError("Nenhum tabuleiro foi detectado na imagem selecionada.")

    contexts = contexts or []
    model, device = get_loaded_model(str(model_path))
    items: list[dict[str, Any]] = []
    for idx, (board_rgb, quad) in enumerate(boards_with_quads):
        oriented = predict_with_orientation(board_rgb, model, device, mode=orientation)  # type: ignore[arg-type]
        prediction = oriented.prediction
        context = contexts[idx] if idx < len(contexts) else None
        side = infer_side_to_move(prediction.fen_board, context)
        resolved = check_position(compose_fen(prediction.fen_board, side))
        items.append(
            {
                "index": idx,
                "board_rgb": board_rgb,
                "quad": quad.tolist() if quad is not None else None,
                "fen_pred": prediction.fen_board,
                "confidence": prediction.mean_confidence,
                "min_confidence": prediction.min_confidence,
                "uncertain_squares": prediction.uncertain_squares,
                # Legalidade ja com o lado a jogar decidido (S-17), e nao com o "w" fixo.
                "is_legal": resolved.is_legal,
                "is_fatal": resolved.is_fatal,
                "problems": resolved.problems,
                "rotation": oriented.rotation,
                "orientation_ambiguous": oriented.ambiguous,
                "orientation_reason": oriented.reason,
                "side_to_move": "w" if side.color else "b",
                "side_to_move_source": side.source,
                "side_conflicting": side.conflicting,
                "exercise_number": context.exercise_number if context else None,
                "caption": context.caption if context else "",
            }
        )
    _set_results(source_rgb=source_rgb, items=items, origin=origin)


def _sample_metadata(idx: int) -> dict[str, Any]:
    """Campos da S-19 para a amostra: lado a jogar e de onde ela veio.

    A origem sai do `result_origin`, que já tem a forma `pdf:<nome>:page:<n>` -- é a única
    coisa que a sessão sabe sobre a procedência, e é melhor gravá-la do que nada.
    """
    items = st.session_state.get("result_items", [])
    item = items[idx] if 0 <= idx < len(items) else {}
    origin = str(st.session_state.get("result_origin", ""))
    source_pdf, source_page = "", ""
    if origin.startswith("pdf:"):
        _, _, resto = origin.partition("pdf:")
        source_pdf, _, page_part = resto.partition(":page:")
        source_page = str(int(page_part) + 1) if page_part.isdigit() else ""

    return {
        "side_to_move": st.session_state.get(f"side_edit_{idx}") or item.get("side_to_move"),
        "source_pdf": source_pdf,
        "source_page": source_page,
        "source_diagram": idx + 1,
        "detection_source": str(item.get("detection_source") or ""),
    }


def _apply_fen_edits_from_dynamic_keys() -> None:
    items = st.session_state.get("result_items")
    fen_edits = st.session_state.get("fen_edits")
    if not items or not fen_edits:
        return

    for idx in range(len(items)):
        key = f"fen_edit_{idx}"
        if key in st.session_state:
            fen_edits[idx] = st.session_state[key]


def _crop_quad_region(source_rgb: np.ndarray, quad: list[list[float]] | None, pad: int = 12) -> np.ndarray | None:
    if quad is None:
        return None
    pts = np.array(quad, dtype=np.float32).reshape(4, 2)
    h, w = source_rgb.shape[:2]
    x0 = max(0, int(np.floor(np.min(pts[:, 0]))) - pad)
    y0 = max(0, int(np.floor(np.min(pts[:, 1]))) - pad)
    x1 = min(w, int(np.ceil(np.max(pts[:, 0]))) + pad)
    y1 = min(h, int(np.ceil(np.max(pts[:, 1]))) + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    return source_rgb[y0:y1, x0:x1]


def _get_selected_fen_for_preview() -> tuple[str | None, int | None]:
    items = st.session_state.get("result_items", [])
    if not items:
        return None, None

    idx = int(st.session_state.get("selected_result_idx", 0))
    idx = max(0, min(idx, len(items) - 1))
    fen_edits = st.session_state.get("fen_edits", [])
    if fen_edits and len(fen_edits) > idx:
        return fen_edits[idx], idx
    return items[idx].get("fen_pred"), idx


def save_current_item(dataset_csv: Path, samples_dir: Path) -> None:
    items = st.session_state.get("result_items", [])
    if not items:
        st.warning("Nao ha OCR para salvar.")
        return

    _apply_fen_edits_from_dynamic_keys()
    idx = int(st.session_state.get("selected_result_idx", 0))
    fen = st.session_state["fen_edits"][idx]
    if not is_valid_fen(fen):
        st.error("FEN atual invalida.")
        return

    try:
        path = append_training_sample(
            board_rgb=items[idx]["board_rgb"],
            fen=fen,
            csv_path=dataset_csv,
            samples_dir=samples_dir,
            **_sample_metadata(idx),
        )
        st.success(f"Diagrama {idx + 1} salvo em: {path}")
    except Exception as exc:
        st.error(f"Falha ao salvar diagrama atual: {exc}")


def save_all_items(dataset_csv: Path, samples_dir: Path) -> None:
    items = st.session_state.get("result_items", [])
    if not items:
        st.warning("Nao ha OCR para salvar.")
        return

    _apply_fen_edits_from_dynamic_keys()
    fen_edits = st.session_state["fen_edits"]
    saved = 0
    invalid = 0
    for idx, item in enumerate(items):
        fen = fen_edits[idx]
        if not is_valid_fen(fen):
            invalid += 1
            continue
        append_training_sample(
            board_rgb=item["board_rgb"],
            fen=fen,
            csv_path=dataset_csv,
            samples_dir=samples_dir,
            **_sample_metadata(idx),
        )
        saved += 1

    if saved:
        st.success(f"Salvos {saved} diagramas.")
    if invalid:
        st.warning(f"{invalid} diagramas nao salvos por FEN invalida.")


def go_to_next_diagram() -> None:
    items = st.session_state.get("result_items", [])
    if not items:
        st.warning("Nao ha diagramas OCR para navegar.")
        return

    current = int(st.session_state.get("selected_result_one_based", 1))
    if current < len(items):
        st.session_state["selected_result_one_based"] = current + 1
    else:
        st.info("Ja esta no ultimo diagrama desta pagina.")
    st.session_state["selected_result_idx"] = int(st.session_state["selected_result_one_based"]) - 1


def show_results_and_actions(dataset_csv: Path, samples_dir: Path, model_path: Path) -> None:
    items = st.session_state.get("result_items", [])
    if not items:
        return

    source_rgb = st.session_state["result_source_rgb"]
    origin = st.session_state["result_origin"]
    fen_edits = st.session_state["fen_edits"]

    st.subheader("Resultados OCR")
    st.caption(f"Origem: {origin} | Diagramas detectados: {len(items)}")
    if "selected_result_one_based" not in st.session_state:
        st.session_state["selected_result_one_based"] = 1
    st.session_state["selected_result_one_based"] = min(
        max(int(st.session_state["selected_result_one_based"]), 1),
        len(items),
    )

    nav1, nav2, nav3, nav4 = st.columns([1, 1, 2, 2])
    with nav1:
        if st.button("Diagrama anterior"):
            st.session_state["selected_result_one_based"] = max(1, st.session_state["selected_result_one_based"] - 1)
    with nav2:
        if st.button("Proximo diagrama"):
            st.session_state["selected_result_one_based"] = min(len(items), st.session_state["selected_result_one_based"] + 1)
    with nav3:
        st.number_input(
            "Diagrama selecionado",
            min_value=1,
            max_value=len(items),
            step=1,
            key="selected_result_one_based",
        )
    with nav4:
        sel_tmp = int(st.session_state["selected_result_one_based"]) - 1
        item_tmp = items[sel_tmp]
        # O minimo vem primeiro: a media fica ~0,97 mesmo com erro e nao alertaria (S-10).
        rotacao = item_tmp.get("rotation")
        st.caption(
            f"Confianca minima: {float(item_tmp.get('min_confidence', 0.0)):.3f}  |  "
            f"media: {float(item_tmp.get('confidence', 0.0)):.3f}"
            + (f"  |  lido a {rotacao} graus" if rotacao else "")
        )
        # Orientacao incerta vem antes da legalidade: se o diagrama estiver de cabeca para
        # baixo, nao ha o que conferir casa por casa (S-13).
        if item_tmp.get("orientation_ambiguous"):
            st.warning(
                f"Orientacao incerta: {item_tmp.get('orientation_reason') or 'as duas eram plausiveis'}. "
                "Confira se o diagrama nao esta de cabeca para baixo.",
                icon="🔄",
            )
        if item_tmp.get("is_legal") is False:
            problems = "; ".join(item_tmp.get("problems") or ())
            if item_tmp.get("is_fatal") is False:
                # O tabuleiro esta bom; o palpite de lado a jogar e que nao fecha (S-17).
                st.info(f"Lado a jogar provavelmente invertido: {problems}", icon="↔️")
            else:
                st.warning(f"Posicao ilegal: {problems or 'motivo nao identificado'}", icon="⚠️")

    st.session_state["selected_result_idx"] = int(st.session_state["selected_result_one_based"]) - 1
    sel = st.session_state["selected_result_idx"]
    fen_sel = st.session_state["fen_edits"][sel]

    compare_left, compare_right = st.columns([1.0, 1.35])
    with compare_left:
        st.caption("Edicao e treino")
    with compare_right:
        st.caption("Comparacao visual (PDF x OCR)")
        crop = _crop_quad_region(source_rgb, items[sel].get("quad"))
        if crop is not None:
            st.image(crop, caption=f"Recorte do diagrama #{sel + 1} no PDF", use_container_width=True)
        else:
            st.info("Nao foi possivel gerar recorte do diagrama no PDF.")
        st.image(items[sel]["board_rgb"], caption=f"Resultado OCR - diagrama #{sel + 1}", use_container_width=True)
        if items[sel]["quad"] is not None:
            st.caption(f"Quad selecionado: {items[sel]['quad']}")

    for idx in range(len(items)):
        key = f"fen_edit_{idx}"
        if key not in st.session_state:
            st.session_state[key] = fen_edits[idx]

    st.text_input(f"FEN diagrama #{sel + 1}", key=f"fen_edit_{sel}")
    _apply_fen_edits_from_dynamic_keys()
    fen_sel = st.session_state["fen_edits"][sel]

    # Lado a jogar visivel e editavel (S-16/S-19), com a procedencia ao lado: "pretas jogam"
    # lido de uma legenda e "pretas jogam" assumido pelo padrao tem valores bem diferentes.
    side_key = f"side_edit_{sel}"
    if side_key not in st.session_state:
        st.session_state[side_key] = str(items[sel].get("side_to_move") or "w")
    side_col, source_col = st.columns([1.0, 1.6])
    with side_col:
        st.radio(
            "Lado a jogar",
            options=("w", "b"),
            format_func=lambda value: "Brancas" if value == "w" else "Pretas",
            key=side_key,
            horizontal=True,
        )
    with source_col:
        rotulos = {
            "text": "declarado no texto do PDF",
            "legality": "deduzido da legalidade da posicao",
            "default": "assumido (o PDF nao diz)",
        }
        if items[sel].get("side_conflicting"):
            st.caption("Origem: texto e posicao discordam — confira.")
        else:
            st.caption(f"Origem: {rotulos.get(str(items[sel].get('side_to_move_source')), 'nao avaliada')}")
        numero = items[sel].get("exercise_number")
        if numero is not None:
            st.caption(f"Exercicio no PDF: {numero}")

    action_col_left, action_col_mid = st.columns([1.0, 1.2])
    with action_col_left:
        if is_valid_fen(fen_sel):
            board = board_from_fen(fen_sel)
            st.code(board.unicode(invert_color=True), language="text")
        else:
            st.code(fen_sel, language="text")

    with action_col_mid:
        epochs = st.number_input("Epocas", min_value=1, max_value=200, value=8, step=1)
        batch_size = st.number_input("Batch size", min_value=16, max_value=512, value=128, step=16)
        lr = st.number_input("Learning rate", min_value=0.00001, max_value=0.05, value=0.001, step=0.0005, format="%.5f")
        if st.button("Treinar modelo"):
            try:
                run = train_model(
                    csv_path=dataset_csv,
                    samples_dir=samples_dir,
                    model_path=model_path,
                    epochs=int(epochs),
                    batch_size=int(batch_size),
                    lr=float(lr),
                    # num_workers=0 obrigatorio aqui: este script nao tem guarda
                    # `if __name__ == "__main__"` -- nao pode ter --, e no Windows cada
                    # worker do DataLoader reimportaria a pagina inteira. Ver
                    # `training.resolve_num_workers`.
                    num_workers=0,
                )
                get_loaded_model.clear()
                st.success(
                    f"Treino concluido em {len(run.history)} epocas. Melhor: epoca {run.best_epoch}, "
                    f"{run.best_metric_name}={run.best_metric:.4f}. Modelo em: {model_path}"
                )
                if run.ece_after is not None:
                    st.caption(
                        f"Calibracao (S-28): T={run.temperature:.4f}, "
                        f"ECE no val {run.ece_before:.5f} -> {run.ece_after:.5f}"
                    )
                st.dataframe(pd.DataFrame(run.history))
            except Exception as exc:
                st.error(f"Falha no treino: {exc}")


st.set_page_config(page_title="Chess Diagram OCR", layout="wide")
st.title("Chess Diagram OCR (OpenCV + PyTorch)")
st.markdown(
    """
    <style>
    /* Mantem a coluna direita (PDF + diagramas) visivel durante scroll */
    div[data-testid="stHorizontalBlock"]:has(h3#pdf-fixo-direita) > div[data-testid="stColumn"]:last-child {
        position: sticky;
        top: 0.75rem;
        z-index: 2;
        align-self: flex-start;
        margin-left: auto;
        background: var(--background-color, rgba(14, 17, 23, 0.01));
        padding-top: 0.1rem;
    }
    @media (max-width: 1100px) {
        div[data-testid="stHorizontalBlock"]:has(h3#pdf-fixo-direita) > div[data-testid="stColumn"]:last-child {
            position: static;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

default_pdf = find_default_pdf_path()

with st.sidebar:
    st.header("Configuracao")
    model_path = Path(st.text_input("Modelo (.pt)", str(DEFAULT_MODEL_PATH)))
    dataset_csv = Path(st.text_input("CSV labels", str(DEFAULT_DATASET_CSV)))
    samples_dir = Path(st.text_input("Pasta samples", str(DEFAULT_SAMPLES_DIR)))
    # Tri-estado em vez de checkbox: "auto" decide por diagrama, o que resolve livro com
    # orientacoes misturadas -- o booleano valia para a pagina inteira (S-13).
    orientation = st.radio(
        "Orientacao do diagrama",
        options=("auto", "0", "180"),
        index=("auto", "0", "180").index(DEFAULT_ORIENTATION_MODE),
        horizontal=True,
        help="auto: escolhe por diagrama pela leitura mais plausivel.",
    )
    dpi = st.slider("DPI render PDF", min_value=120, max_value=320, value=220, step=20)
    max_boards = st.number_input(
        "Max diagramas detectados", min_value=1, max_value=30, value=DEFAULT_MAX_BOARDS, step=1
    )
    if st.button("Recarregar modelo"):
        get_loaded_model.clear()
        st.success("Cache do modelo limpo. OCR vai usar o .pt mais recente.")
    st.info(f"O OCR usa o modelo salvo em: {model_path}")

mode = st.radio("Fonte do PDF", ["Arquivo local", "Upload"], horizontal=True)
pdf_source: Any = None
pdf_name = None

if mode == "Arquivo local":
    default_pdf_text = str(default_pdf) if default_pdf is not None else ""
    pdf_path = Path(st.text_input("Caminho PDF", default_pdf_text)) if default_pdf_text else None
    if pdf_path is not None and pdf_path.exists():
        pdf_source = pdf_path
        pdf_name = pdf_path.name
    else:
        st.warning("Arquivo PDF nao encontrado. Informe um caminho valido ou use Upload.")
else:
    uploaded_pdf = st.file_uploader("Envie o PDF", type=["pdf"])
    if uploaded_pdf is not None:
        pdf_source = uploaded_pdf.getvalue()
        pdf_name = uploaded_pdf.name

tab_pdf, tab_local = st.tabs(["OCR PDF", "OCR imagem local"])

with tab_pdf:
    if pdf_source is None:
        st.info("Selecione um PDF para usar navegacao por paginas.")
    else:
        try:
            page_count = get_pdf_page_count(pdf_source)
        except Exception as exc:
            st.error(f"Falha ao abrir PDF: {exc}")
            page_count = 0

        if page_count > 0:
            st.caption(f"PDF: {pdf_name} | Paginas: {page_count}")

            if "page_index" not in st.session_state:
                st.session_state["page_index"] = 0
            st.session_state["page_index"] = min(max(st.session_state["page_index"], 0), page_count - 1)

            layout_left, layout_right = st.columns([1.0, 1.25])
            with layout_left:
                n1, n2, n3 = st.columns([1, 1, 2])
                with n1:
                    if st.button("Pagina anterior"):
                        st.session_state["page_index"] = max(0, st.session_state["page_index"] - 1)
                with n2:
                    if st.button("Proxima pagina"):
                        st.session_state["page_index"] = min(page_count - 1, st.session_state["page_index"] + 1)
                with n3:
                    st.number_input(
                        "Pagina (0-index)",
                        min_value=0,
                        max_value=page_count - 1,
                        step=1,
                        key="page_index",
                    )

                a1, a2 = st.columns(2)
                with a1:
                    run_best = st.button("OCR melhor diagrama", type="primary")
                with a2:
                    run_all = st.button("OCR todos diagramas da pagina", type="primary")
                preview_container = st.container()

            with layout_right:
                st.subheader("PDF fixo (direita)")
                try:
                    page_preview_rgb = render_pdf_page_cached(pdf_source, int(st.session_state["page_index"]), dpi=dpi)
                    st.image(page_preview_rgb, caption=f"Pagina {st.session_state['page_index']}", use_container_width=True)
                except Exception as exc:
                    st.error(f"Falha ao renderizar pagina: {exc}")
                    page_preview_rgb = None

            if run_best or run_all:
                try:
                    if page_preview_rgb is None:
                        page_rgb = render_pdf_page_cached(pdf_source, int(st.session_state["page_index"]), dpi=dpi)
                    else:
                        page_rgb = page_preview_rgb
                    # Pagina de PDF usa o detector das duas fontes, o mesmo da exportacao
                    # (S-12): GUI e PGN precisam recortar e numerar o mesmo diagrama.
                    page_index = int(st.session_state["page_index"])
                    candidates = detect_diagrams_in_pdf_page(
                        pdf_source,
                        page_index,
                        page_rgb,
                        max_boards=(int(max_boards) if run_all else 1),
                    )
                    boards = [(candidate.board_rgb, None) for candidate in candidates]
                    run_ocr_for_boards(
                        source_rgb=page_rgb,
                        boards_with_quads=boards,
                        model_path=model_path,
                        orientation=orientation,
                        origin=f"pdf:{pdf_name}:page:{page_index}",
                        # Mesmo contexto textual da exportacao (S-16).
                        contexts=contexts_for_pdf_page(pdf_source, page_index, [c.bbox_pdf for c in candidates]),
                    )
                except Exception as exc:
                    st.error(f"Falha no OCR da pagina: {exc}")

            with preview_container:
                st.subheader("Reconhecido (SVG)")
                preview_fen, preview_idx = _get_selected_fen_for_preview()
                if preview_fen is None:
                    st.info("Rode OCR para exibir o board reconhecido aqui.")
                elif is_valid_fen(preview_fen):
                    preview_board = board_from_fen(preview_fen)
                    preview_svg = chess.svg.board(board=preview_board, size=460)
                    components.html(preview_svg, height=480)
                    st.caption(f"Diagrama selecionado: #{int(preview_idx) + 1}")
                else:
                    st.error("FEN do diagrama selecionado esta invalida.")

                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("Salvar diagrama atual", key="top_save_current"):
                        save_current_item(dataset_csv=dataset_csv, samples_dir=samples_dir)
                with b2:
                    if st.button("Salvar todos", key="top_save_all"):
                        save_all_items(dataset_csv=dataset_csv, samples_dir=samples_dir)
                with b3:
                    if st.button("Proximo diagrama", key="top_next_diagram"):
                        go_to_next_diagram()

with tab_local:
    st.caption("Use para OCR de print, recorte ou foto. Pode detectar mais de um tabuleiro.")
    uploaded_image = st.file_uploader("Envie imagem", type=["png", "jpg", "jpeg", "webp"], key="local_image_uploader")
    board_only = st.checkbox("Imagem ja contem somente um tabuleiro", value=False)
    local_all = st.checkbox("Detectar todos diagramas da imagem", value=True)
    run_local = st.button("Fazer OCR local", type="primary")

    if run_local:
        if uploaded_image is None:
            st.warning("Envie uma imagem antes de rodar OCR local.")
        else:
            data = np.frombuffer(uploaded_image.getvalue(), dtype=np.uint8)
            image_bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image_bgr is None:
                st.error("Nao foi possivel abrir a imagem.")
            else:
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                try:
                    if board_only:
                        boards = [(image_rgb, None)]
                    else:
                        boards = detect_boards(
                            image_rgb=image_rgb,
                            max_boards=(int(max_boards) if local_all else 1),
                        )
                    run_ocr_for_boards(
                        source_rgb=image_rgb,
                        boards_with_quads=boards,
                        model_path=model_path,
                        orientation=orientation,
                        origin=f"local-image:{uploaded_image.name}",
                    )
                except Exception as exc:
                    st.error(f"Falha no OCR local: {exc}")

show_results_and_actions(dataset_csv=dataset_csv, samples_dir=samples_dir, model_path=model_path)
