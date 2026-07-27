"""Frontend Streamlit. Apresentação apenas: o pipeline mora em `service.py` (S-31).

Este arquivo tinha a sua própria versão de `run_ocr_for_boards`, e ela já divergia da do
Tkinter: não refinava o recorte pelo contorno, montava a legalidade com `w` fixo antes da
Fase 3, e descartava a matriz por casa -- então nunca poderia mostrar em que casa o modelo
esteve inseguro. Agora as duas telas chamam o mesmo `OcrService` e recebem o mesmo
`RecognizedDiagram`; o que cada uma faz de diferente é desenhar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chess.svg
import cv2
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from chess_diagram_ocr.config import (
    DEFAULT_DATASET_CSV,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_SAMPLES_DIR,
    find_default_pdf_path,
)
from chess_diagram_ocr.fen_utils import board_from_fen, is_valid_fen, square_name
from chess_diagram_ocr.service import (
    OcrService,
    RecognitionOptions,
    RecognitionOrigin,
    RecognizedDiagram,
)
from chess_diagram_ocr.training import train_model


@st.cache_resource(show_spinner=False)
def get_service() -> OcrService:
    """Um serviço por sessão do Streamlit, com o modelo carregado uma vez só.

    `cache_resource` porque o modelo não é serializável e não deve ser: `cache_data`
    tentaria copiá-lo a cada rerun.
    """
    return OcrService()


@st.cache_data(show_spinner=False)
def render_pdf_page_cached(pdf_source: Any, page_index: int, dpi: int) -> np.ndarray:
    return get_service().render_page(pdf_source, page_index, dpi=dpi)


def _set_results(source_rgb: np.ndarray, items: list[RecognizedDiagram], origin: RecognitionOrigin) -> None:
    _clear_results()
    st.session_state["result_source_rgb"] = source_rgb
    st.session_state["result_items"] = items
    st.session_state["result_origin"] = origin
    st.session_state["selected_result_idx"] = 0
    st.session_state["selected_result_one_based"] = 1
    st.session_state["fen_edits"] = [item.placement for item in items]


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


def _items() -> list[RecognizedDiagram]:
    return list(st.session_state.get("result_items", []))


def _recognition_options(max_boards: int, **overrides: Any) -> RecognitionOptions:
    return RecognitionOptions(
        model_path=model_path,
        orientation=orientation,
        max_boards=max_boards,
        dpi=int(dpi),
        **overrides,
    )


def _apply_fen_edits_from_dynamic_keys() -> None:
    items = _items()
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
    items = _items()
    if not items:
        return None, None

    idx = int(st.session_state.get("selected_result_idx", 0))
    idx = max(0, min(idx, len(items) - 1))
    fen_edits = st.session_state.get("fen_edits", [])
    if fen_edits and len(fen_edits) > idx:
        return fen_edits[idx], idx
    return items[idx].placement, idx


def _save_one(idx: int, fen: str, dataset_csv: Path, samples_dir: Path) -> Path:
    items = _items()
    return get_service().save_sample(
        items[idx],
        fen,
        csv_path=dataset_csv,
        samples_dir=samples_dir,
        origin=st.session_state.get("result_origin"),
        side_to_move=st.session_state.get(f"side_edit_{idx}") or items[idx].side_to_move,
    )


def save_current_item(dataset_csv: Path, samples_dir: Path) -> None:
    items = _items()
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
        path = _save_one(idx, fen, dataset_csv, samples_dir)
        st.success(f"Diagrama {idx + 1} salvo em: {path}")
    except Exception as exc:
        st.error(f"Falha ao salvar diagrama atual: {exc}")


def save_all_items(dataset_csv: Path, samples_dir: Path) -> None:
    items = _items()
    if not items:
        st.warning("Nao ha OCR para salvar.")
        return

    _apply_fen_edits_from_dynamic_keys()
    fen_edits = st.session_state["fen_edits"]
    saved = 0
    invalid = 0
    for idx in range(len(items)):
        fen = fen_edits[idx]
        if not is_valid_fen(fen):
            invalid += 1
            continue
        _save_one(idx, fen, dataset_csv, samples_dir)
        saved += 1

    if saved:
        st.success(f"Salvos {saved} diagramas.")
    if invalid:
        st.warning(f"{invalid} diagramas nao salvos por FEN invalida.")


def go_to_next_diagram() -> None:
    items = _items()
    if not items:
        st.warning("Nao ha diagramas OCR para navegar.")
        return

    current = int(st.session_state.get("selected_result_one_based", 1))
    if current < len(items):
        st.session_state["selected_result_one_based"] = current + 1
    else:
        st.info("Ja esta no ultimo diagrama desta pagina.")
    st.session_state["selected_result_idx"] = int(st.session_state["selected_result_one_based"]) - 1


def _show_diagram_signals(item: RecognizedDiagram) -> None:
    """Os sinais das Fases 2 e 3 que esta tela descartava por montar o próprio dicionário."""
    # O minimo vem primeiro: a media fica ~0,97 mesmo com erro e nao alertaria (S-10).
    partes = [
        f"Confianca minima: {item.min_confidence:.3f}",
        f"media: {item.mean_confidence:.3f}",
    ]
    if item.rotation:
        partes.append(f"lido a {item.rotation} graus")
    if item.detection_source:
        partes.append(f"deteccao: {item.detection_source}")
    st.caption("  |  ".join(partes))

    # Orientacao incerta vem antes da legalidade: se o diagrama estiver de cabeca para
    # baixo, nao ha o que conferir casa por casa (S-13).
    if item.orientation_ambiguous:
        st.warning(
            f"Orientacao incerta: {item.orientation_reason or 'as duas eram plausiveis'}. "
            "Confira se o diagrama nao esta de cabeca para baixo.",
            icon="🔄",
        )

    if item.is_legal is False:
        problems = "; ".join(item.problems)
        if item.is_fatal is False:
            # O tabuleiro esta bom; o palpite de lado a jogar e que nao fecha (S-17).
            st.info(f"Lado a jogar provavelmente invertido: {problems}", icon="↔️")
        else:
            st.warning(f"Posicao ilegal: {problems or 'motivo nao identificado'}", icon="⚠️")

    # Sem tabuleiro interativo aqui, o heatmap da S-21 vira lista de casas -- que e a mesma
    # informacao, e era o que faltava por completo nesta tela.
    if item.uncertain_squares:
        nomes = ", ".join(square_name(casa) for casa in item.uncertain_squares[:8])
        sufixo = f" (+{len(item.uncertain_squares) - 8})" if len(item.uncertain_squares) > 8 else ""
        st.caption(f"Casas inseguras: {nomes}{sufixo}")
    if item.changed_squares:
        nomes = ", ".join(square_name(casa) for casa in item.changed_squares)
        st.caption(f"Casas corrigidas pela decodificacao com restricoes (S-11): {nomes}")


def show_results_and_actions(dataset_csv: Path, samples_dir: Path, model_path: Path) -> None:
    items = _items()
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
        _show_diagram_signals(items[int(st.session_state["selected_result_one_based"]) - 1])

    st.session_state["selected_result_idx"] = int(st.session_state["selected_result_one_based"]) - 1
    sel = st.session_state["selected_result_idx"]

    compare_left, compare_right = st.columns([1.0, 1.35])
    with compare_left:
        st.caption("Edicao e treino")
    with compare_right:
        st.caption("Comparacao visual (PDF x OCR)")
        crop = _crop_quad_region(source_rgb, items[sel].quad)
        if crop is not None:
            st.image(crop, caption=f"Recorte do diagrama #{sel + 1} no PDF", use_container_width=True)
        else:
            st.info("Nao foi possivel gerar recorte do diagrama no PDF.")
        st.image(items[sel].board_rgb, caption=f"Resultado OCR - diagrama #{sel + 1}", use_container_width=True)
        if items[sel].quad is not None:
            st.caption(f"Quad selecionado: {items[sel].quad}")

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
        st.session_state[side_key] = items[sel].side_to_move
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
            "manual": "definido por voce",
            "queue": "vindo da fila de revisao",
        }
        if items[sel].side_conflicting:
            st.caption("Origem: texto e posicao discordam — confira.")
        else:
            fonte = rotulos.get(items[sel].side_to_move_source, "nao avaliada")
            motivo = items[sel].side_to_move_reason
            st.caption(f"Origem: {fonte}" + (f" ({motivo})" if motivo else ""))
        if items[sel].exercise_number is not None:
            st.caption(f"Exercicio no PDF: {items[sel].exercise_number}")
        if items[sel].caption:
            st.caption(f"Legenda: {items[sel].caption}")

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
                # Espera o OCR em andamento antes de trocar o modelo, em vez de disputar
                # com ele: o treino acabou de reescrever este mesmo `.pt` (S-31).
                get_service().invalidate_model(model_path)
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
        get_service().invalidate_model(model_path)
        st.success("Cache do modelo limpo. OCR vai usar o .pt mais recente.")
    st.info(f"O OCR usa o modelo salvo em: {model_path}")
    # S-30: o dispositivo era escolhido em silencio, entao uma maquina com placa mas com o
    # torch +cpu instalado rodava em CPU sem nada dizer.
    st.caption(f"Dispositivo: {get_service().device_label}")

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
            page_count = get_service().page_count(pdf_source)
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
                    page_index = int(st.session_state["page_index"])
                    if page_preview_rgb is None:
                        page_rgb = render_pdf_page_cached(pdf_source, page_index, dpi=dpi)
                    else:
                        page_rgb = page_preview_rgb
                    # `recognize_page` e o detector das duas fontes (S-12), o mesmo que a
                    # exportacao usa: GUI e PGN precisam recortar e numerar o mesmo diagrama.
                    diagramas = get_service().recognize_page(
                        pdf_source,
                        page_index,
                        page_rgb,
                        options=_recognition_options(int(max_boards) if run_all else 1),
                    )
                    _set_results(
                        source_rgb=page_rgb,
                        items=diagramas,
                        origin=RecognitionOrigin.for_page(str(pdf_name), page_index),
                    )
                except Exception as exc:
                    _clear_results()
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
                    # `refine_detected_boards` alinha o recorte pelo contorno dentro do quad.
                    # Estava so no Tkinter, e e o que decide se a grade 8x8 cai em registro.
                    diagramas = get_service().recognize_image(
                        image_rgb,
                        options=_recognition_options(
                            int(max_boards) if local_all else 1,
                            refine_detected_boards=True,
                        ),
                        boards=[(image_rgb, None)] if board_only else None,
                    )
                    _set_results(
                        source_rgb=image_rgb,
                        items=diagramas,
                        origin=RecognitionOrigin.for_image(uploaded_image.name),
                    )
                except Exception as exc:
                    _clear_results()
                    st.error(f"Falha no OCR local: {exc}")

show_results_and_actions(dataset_csv=dataset_csv, samples_dir=samples_dir, model_path=model_path)
