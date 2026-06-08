from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from android.permissions import request_permissions, Permission
from jnius import autoclass

# Android MediaProjection で画面キャプチャ
# WebSocketでサーバーに送信

import threading
import websocket
import base64
import json

class ScreenShareApp(App):
    def build(self):
        request_permissions([Permission.RECORD_AUDIO, Permission.INTERNET])
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.status = Label(text='待機中')
        self.code_input = TextInput(hint_text='接続コード（6桁）', multiline=False)
        btn_host = Button(text='配信開始', on_press=self.start_host)
        btn_view = Button(text='視聴開始', on_press=self.start_view)
        layout.add_widget(self.status)
        layout.add_widget(self.code_input)
        layout.add_widget(btn_host)
        layout.add_widget(btn_view)
        return layout

    def start_host(self, *a):
        self.status.text = '配信中...'

    def start_view(self, *a):
        self.status.text = '接続中...'

ScreenShareApp().run()
