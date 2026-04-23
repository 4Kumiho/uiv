import os
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder

Builder.load_file(os.path.join(os.path.dirname(__file__), "main_screen.kv"))


class MainScreen(Screen):
    SCREEN_NAME = "main"

    def go_designer(self):
        self.manager.transition.direction = "left"
        self.manager.current = "designer_create"

    def go_designer_open(self):
        self.manager.transition.direction = "left"
        self.manager.current = "designer_open"

    def go_executor(self):
        self.manager.transition.direction = "left"
        self.manager.current = "executor_create"

    def go_executor_open(self):
        self.manager.transition.direction = "left"
        self.manager.current = "executor_open"

    def go_ambient(self):
        self.manager.transition.direction = "left"
        self.manager.current = "ambient_init"
