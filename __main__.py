import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from src.app.menu_pages.main_screen.main_screen import MainScreen
from src.app.designer_pages.create_screen.designer_create import DesignerCreateScreen
from src.app.designer_pages.open_screen.designer_open import DesignerOpenScreen
from src.app.designer_pages.summary_screen.designer_summary import DesignerSummaryScreen
from src.app.executor_pages.create_screen.executor_create import ExecutorCreateScreen
from src.app.executor_pages.open_screen.executor_open import ExecutorOpenScreen


class UIValidatorApp(App):

    def build(self):
        self.title = "UI-Validator"
        self.icon = os.path.join(PROJECT_ROOT, "src", "app", "assets", "app_icon.png")
        Window.clearcolor = (0.05, 0.05, 0.10, 1)

        sm = ScreenManager(transition=SlideTransition(duration=0.20))

        sm.add_widget(MainScreen(name=MainScreen.SCREEN_NAME))
        sm.add_widget(DesignerCreateScreen(name=DesignerCreateScreen.SCREEN_NAME))
        sm.add_widget(DesignerOpenScreen(name=DesignerOpenScreen.SCREEN_NAME))
        sm.add_widget(DesignerSummaryScreen(name=DesignerSummaryScreen.SCREEN_NAME))
        
        sm.add_widget(ExecutorCreateScreen(name=ExecutorCreateScreen.SCREEN_NAME))
        sm.add_widget(ExecutorOpenScreen(name=ExecutorOpenScreen.SCREEN_NAME))
        sm.current = MainScreen.SCREEN_NAME

        return sm


if __name__ == "__main__":
    UIValidatorApp().run()
