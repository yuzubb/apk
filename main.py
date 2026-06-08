import threading
import json
import base64
import io
import time

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.utils import platform

if platform == 'android':
    from android.permissions import request_permissions, Permission
    from jnius import autoclass, cast
    from android import activity

import websocket

WS_URL = "wss://alto-ashley-rescue-surf.trycloudflare.com/ws"

# Android classes
if platform == 'android':
    MediaProjectionManager = autoclass('android.media.projection.MediaProjectionManager')
    ImageReader = autoclass('android.media.ImageReader')
    PixelFormat = autoclass('android.graphics.PixelFormat')
    Context = autoclass('android.content.Context')
    Intent = autoclass('android.content.Intent')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')


class ScreenShareApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.ws = None
        self.role = None
        self.code = None
        self.capturing = False
        self.media_projection = None

    def build(self):
        if platform == 'android':
            request_permissions([Permission.INTERNET, Permission.RECORD_AUDIO])

        root = BoxLayout(orientation='vertical', padding=24, spacing=12)

        self.status_label = Label(
            text='モードを選択してください',
            font_size='14sp',
            size_hint_y=None,
            height=40,
            color=(0.7, 0.7, 1, 1)
        )

        self.code_label = Label(
            text='',
            font_size='32sp',
            bold=True,
            size_hint_y=None,
            height=60,
            color=(1, 1, 1, 1)
        )

        self.code_input = TextInput(
            hint_text='6桁のコードを入力',
            multiline=False,
            input_filter='int',
            font_size='24sp',
            size_hint_y=None,
            height=56,
            halign='center'
        )

        btn_grid = GridLayout(cols=2, spacing=8, size_hint_y=None, height=56)
        self.btn_host = Button(
            text='配信する',
            background_color=(0.48, 0.42, 0.98, 1),
            on_press=self.start_host
        )
        self.btn_view = Button(
            text='視聴する',
            background_color=(0.2, 0.2, 0.3, 1),
            on_press=self.start_view
        )
        btn_grid.add_widget(self.btn_host)
        btn_grid.add_widget(self.btn_view)

        self.btn_stop = Button(
            text='停止',
            background_color=(0.8, 0.2, 0.2, 1),
            size_hint_y=None,
            height=48,
            on_press=self.stop_all
        )
        self.btn_stop.opacity = 0
        self.btn_stop.disabled = True

        root.add_widget(self.status_label)
        root.add_widget(self.code_label)
        root.add_widget(self.code_input)
        root.add_widget(btn_grid)
        root.add_widget(self.btn_stop)

        return root

    def set_status(self, txt):
        Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', txt))

    # ---- HOST ----
    def start_host(self, *a):
        self.role = 'host'
        self.set_status('サーバーに接続中...')
        self.btn_host.disabled = True
        self.btn_view.disabled = True

        if platform == 'android':
            self._request_media_projection()
        else:
            threading.Thread(target=self._ws_connect_host, daemon=True).start()

    def _request_media_projection(self):
        mpm = cast(
            MediaProjectionManager,
            PythonActivity.mActivity.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
        )
        intent = mpm.createScreenCaptureIntent()
        activity.bind(on_activity_result=self._on_projection_result)
        PythonActivity.mActivity.startActivityForResult(intent, 1001)

    def _on_projection_result(self, requestCode, resultCode, data):
        if requestCode == 1001 and resultCode == -1:  # RESULT_OK
            MediaProjection = autoclass('android.media.projection.MediaProjection')
            mpm = cast(
                MediaProjectionManager,
                PythonActivity.mActivity.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
            )
            self.media_projection = mpm.getMediaProjection(resultCode, data)
            threading.Thread(target=self._ws_connect_host, daemon=True).start()
        else:
            self.set_status('画面キャプチャが拒否されました')
            self.btn_host.disabled = False
            self.btn_view.disabled = False

    def _ws_connect_host(self):
        try:
            self.ws = websocket.WebSocketApp(
                WS_URL,
                on_open=lambda ws: ws.send(json.dumps({'type': 'create'})),
                on_message=self._on_message,
                on_error=lambda ws, e: self.set_status(f'エラー: {e}'),
                on_close=lambda ws, c, m: self.set_status('切断されました')
            )
            self.ws.run_forever()
        except Exception as e:
            self.set_status(f'接続失敗: {e}')

    # ---- VIEWER ----
    def start_view(self, *a):
        code = self.code_input.text.strip()
        if len(code) != 6:
            self.set_status('6桁のコードを入力してください')
            return
        self.role = 'viewer'
        self.code = code
        self.set_status('サーバーに接続中...')
        self.btn_host.disabled = True
        self.btn_view.disabled = True
        threading.Thread(target=self._ws_connect_viewer, daemon=True).start()

    def _ws_connect_viewer(self):
        try:
            self.ws = websocket.WebSocketApp(
                WS_URL,
                on_open=lambda ws: ws.send(json.dumps({'type': 'join', 'code': self.code})),
                on_message=self._on_message,
                on_error=lambda ws, e: self.set_status(f'エラー: {e}'),
                on_close=lambda ws, c, m: self.set_status('切断されました')
            )
            self.ws.run_forever()
        except Exception as e:
            self.set_status(f'接続失敗: {e}')

    # ---- WS MESSAGE ----
    def _on_message(self, ws, raw):
        msg = json.loads(raw)
        t = msg.get('type')

        if t == 'created':
            self.code = msg['code']
            Clock.schedule_once(lambda dt: setattr(self.code_label, 'text', self.code))
            self.set_status('待機中 — コードを相手に教えてください')
            Clock.schedule_once(self._show_stop)

        elif t == 'viewer_joined':
            self.set_status('ビューワーが参加 — 配信開始')
            self.capturing = True
            if platform == 'android' and self.media_projection:
                threading.Thread(target=self._capture_loop, daemon=True).start()

        elif t == 'joined':
            self.set_status('接続しました — 映像を待っています')
            Clock.schedule_once(self._show_stop)

        elif t == 'frame':
            # 受信側: base64フレームを表示（簡易実装）
            self.set_status('受信中...')

        elif t == 'host_disconnected':
            self.set_status('配信者が切断しました')
            self.stop_all()

        elif t == 'error':
            self.set_status('エラー: ' + msg.get('msg', ''))

    def _show_stop(self, *a):
        self.btn_stop.opacity = 1
        self.btn_stop.disabled = False

    # ---- CAPTURE LOOP (Android) ----
    def _capture_loop(self):
        DisplayMetrics = autoclass('android.util.DisplayMetrics')
        metrics = DisplayMetrics()
        PythonActivity.mActivity.getWindowManager().getDefaultDisplay().getMetrics(metrics)
        W, H = metrics.widthPixels, metrics.heightPixels

        reader = ImageReader.newInstance(W // 2, H // 2, PixelFormat.RGBA_8888, 2)
        surface = reader.getSurface()

        vd = self.media_projection.createVirtualDisplay(
            'ScreenShare', W // 2, H // 2, metrics.densityDpi,
            autoclass('android.hardware.display.DisplayManager').VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            surface, None, None
        )

        Bitmap = autoclass('android.graphics.Bitmap')
        ByteArrayOutputStream = autoclass('java.io.ByteArrayOutputStream')

        while self.capturing:
            try:
                img = reader.acquireLatestImage()
                if img is None:
                    time.sleep(0.033)
                    continue

                planes = img.getPlanes()
                buf = planes[0].getBuffer()
                buf.rewind()
                bmp = Bitmap.createBitmap(W // 2, H // 2, Bitmap.Config.ARGB_8888)
                bmp.copyPixelsFromBuffer(buf)
                img.close()

                baos = ByteArrayOutputStream()
                bmp.compress(autoclass('android.graphics.Bitmap$CompressFormat').JPEG, 50, baos)
                b64 = base64.b64encode(bytes(baos.toByteArray())).decode()

                if self.ws:
                    self.ws.send(json.dumps({'type': 'frame', 'data': b64}))

                time.sleep(0.033)  # ~30fps
            except Exception:
                time.sleep(0.1)

        vd.release()
        reader.close()

    # ---- STOP ----
    def stop_all(self, *a):
        self.capturing = False
        if self.ws:
            self.ws.close()
            self.ws = None
        self.media_projection = None
        self.role = None
        self.code = None
        Clock.schedule_once(lambda dt: setattr(self.code_label, 'text', ''))
        self.set_status('モードを選択してください')
        Clock.schedule_once(lambda dt: setattr(self.btn_host, 'disabled', False))
        Clock.schedule_once(lambda dt: setattr(self.btn_view, 'disabled', False))
        Clock.schedule_once(lambda dt: setattr(self.btn_stop, 'opacity', 0))
        Clock.schedule_once(lambda dt: setattr(self.btn_stop, 'disabled', True))


ScreenShareApp().run()
