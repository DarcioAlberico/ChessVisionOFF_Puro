from __future__ import annotations

import ctypes
import logging
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

USER32 = ctypes.windll.user32


class WebView2SupportError(RuntimeError):
    pass


class EmbeddedWebView2:
    """Hospeda um WebView2 dentro de um widget Tk, via Windows Forms e pythonnet.

    Os objetos vindos do interop .NET (`Control`, `EdgeChrome`, `Window`, `Thread` do
    System.Threading) sao dinamicos e nao tem stubs de tipo: por isso estao anotados
    como `Any`. `host_widget` e um widget Tk, mantido generico para nao acoplar o
    modulo ao tkinter.
    """

    def __init__(self, host_widget: Any, error_cb: Callable[[str], None] | None = None) -> None:
        self.host_widget = host_widget
        self.error_cb = error_cb
        self._thread: Any = None
        self._host_control: Any = None
        self._edge: Any = None
        self._window: Any = None
        self._ready_event = threading.Event()
        self._init_error: str | None = None
        self._current_url: str | None = None
        self._destroyed = False
        self._parent_hwnd = 0
        self._initial_size = (1, 1)
        self._exit_thread: Any = None
        self._invoke: Any = None

    @staticmethod
    def is_supported() -> tuple[bool, str]:
        try:
            from webview.platforms.winforms import _is_chromium
        except Exception as exc:
            return False, f"Dependencias do WebView2 indisponiveis: {exc}"

        if not _is_chromium():
            return False, "Microsoft Edge WebView2 Runtime nao encontrado."

        return True, ""

    def ensure_started(self) -> None:
        if self._destroyed:
            raise WebView2SupportError("Visualizador WebView2 ja foi encerrado.")
        if self._thread is not None:
            self._raise_if_init_failed()
            return

        supported, reason = self.is_supported()
        if not supported:
            raise WebView2SupportError(reason)

        self.host_widget.update_idletasks()
        self._parent_hwnd = int(self.host_widget.winfo_id())
        self._initial_size = (
            max(1, int(self.host_widget.winfo_width())),
            max(1, int(self.host_widget.winfo_height())),
        )
        import clr

        clr.AddReference("System.Threading")
        from System.Threading import ApartmentState, Thread, ThreadStart

        self._thread = Thread(ThreadStart(self._run_sta_thread))
        self._thread.Name = "WebView2Host"
        self._thread.IsBackground = True
        self._thread.ApartmentState = ApartmentState.STA
        self._thread.Start()
        self._ready_event.wait(timeout=15)
        self._raise_if_init_failed()

    def load_pdf(self, pdf_path: Path, page_index: int = 0) -> None:
        page = max(0, int(page_index)) + 1
        url = pdf_path.resolve().as_uri() + f"#page={page}"
        self.load_url(url)

    def load_url(self, url: str) -> None:
        self._current_url = url
        self.ensure_started()
        self._invoke(lambda: self._edge.load_url(url))

    def refresh(self) -> None:
        if self._host_control is None:
            return
        self._invoke(lambda: self._edge.webview.Reload())

    def show(self) -> None:
        if self._host_control is None:
            return
        self._invoke(lambda: self._host_control.Show())
        self.resize()

    def hide(self) -> None:
        if self._host_control is None:
            return
        self._invoke(lambda: self._host_control.Hide())

    def resize(self) -> None:
        if self._host_control is None:
            return
        width = max(1, int(self.host_widget.winfo_width()))
        height = max(1, int(self.host_widget.winfo_height()))
        USER32.MoveWindow(int(str(self._host_control.Handle)), 0, 0, width, height, True)

    def destroy(self) -> None:
        self._destroyed = True
        if self._host_control is None:
            return
        try:
            def _shutdown() -> None:
                if self._exit_thread is not None:
                    self._exit_thread()
                self._host_control.Dispose()

            self._invoke(_shutdown)
        except Exception as exc:  # noqa: BLE001 - interop .NET levanta tipos arbitrarios
            # O encerramento e best-effort: o processo esta saindo de qualquer forma.
            logger.warning("Falha ao encerrar o painel WebView2: %s", exc)
        self._thread = None
        self._host_control = None
        self._edge = None
        self._window = None
        self._exit_thread = None

    def _raise_if_init_failed(self) -> None:
        if self._init_error is not None:
            raise WebView2SupportError(self._init_error)

    def _run_sta_thread(self) -> None:
        try:
            import clr

            clr.AddReference("System.Windows.Forms")
            from System import Action
            from System.Windows.Forms import Application, ApplicationContext, Control
            from webview.platforms.edgechromium import EdgeChrome
            from webview.window import Window

            parent_hwnd = self._parent_hwnd
            width, height = self._initial_size

            host_control = Control()
            host_control.Width = width
            host_control.Height = height

            window = Window(
                f"embedded-{uuid.uuid4().hex[:8]}",
                "Embedded WebView2",
                url=self._current_url,
                # pywebview aceita None em html/js_api, mas anota como str: ignore necessario.
                html=None,  # type: ignore[arg-type]
                js_api=None,
                width=width,
                height=height,
                x=None,
                y=None,
                resizable=True,
                fullscreen=False,
                min_size=(200, 100),
                hidden=False,
                frameless=False,
                easy_drag=True,
                minimized=False,
                on_top=False,
                confirm_close=False,
                background_color="#FFFFFF",
                transparent=False,
                text_select=True,
                localization=None,
                zoomable=True,
                draggable=True,
                vibrancy=False,
            )
            # Terceiro argumento (user_agent) e opcional em tempo de execucao.
            edge = EdgeChrome(host_control, window, None)  # type: ignore[arg-type]

            control_handle = int(str(host_control.Handle))
            USER32.SetParent(control_handle, parent_hwnd)
            USER32.MoveWindow(control_handle, 0, 0, width, height, True)

            app_context = ApplicationContext()

            self._host_control = host_control
            self._edge = edge
            self._window = window
            self._invoke = lambda callback: host_control.BeginInvoke(Action(callback))
            self._exit_thread = app_context.ExitThread
            self._ready_event.set()

            Application.Run(app_context)
        except Exception as exc:
            self._init_error = str(exc)
            self._ready_event.set()
            if self.error_cb is not None:
                self.error_cb(self._init_error)
