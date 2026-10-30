from . import DEFAULT_THEME
import os
import sys

def main():
    from .single_instance import InstanceGuard, already_running
    # Keep this descriptor until process exit, including tray use and shutdown.
    # CLOEXEC lets renderer/update launchers start after this process exits.
    instance = InstanceGuard()
    if not instance.acquire():
        sys.exit(already_running(restarting=instance.restarting))
    from . import profiles
    profiles.initialize()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from . import APP_NAME, distro, i18n, sensors, settings, theme, diagnostics, hover_hints
    from .logo import load_logo
    from .brand import app_icon
    from .wallpaper_accents import resolve_accent
    from . import renderer, eco
    from .update_manager import UpdateManager
    sys.excepthook = diagnostics.exception_hook
    diagnostics.enable_native_crash_trace()
    # Select the scene-graph backend before the first Quick window exists.
    renderer.prepare_start()
    app = QApplication(sys.argv)
    # Disable transient hover help across the entire application, not just navigation.
    app._vitalux_hover_guard = hover_hints.install(app)
    # Hiding the final window must not kill the tray icon and sampler.
    # MainWindow.closeEvent explicitly quits on a genuine Exit command.
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME+'-Unstable' if profiles.installed()=='unstable' else APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Desktop-portal app IDs require an installed .desktop entry; avoid asking
    # the portal to register an unknown ID when using Vitalux portably.
    xdg_data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    if os.path.isfile(os.path.join(xdg_data, "applications", "vitalux.desktop")):
        app.setDesktopFileName("vitalux")
    lang = settings.get("lang") or ("de" if os.environ.get("LANG", "").lower().startswith("de") else "en")
    i18n.set_lang(lang)
    info = distro.info()
    settings.migrate_crystal_designs()
    requested_theme = settings.get('theme', DEFAULT_THEME)
    theme.set_mode('minimal' if eco.enabled() else requested_theme)
    if not eco.enabled() and requested_theme != theme.mode():
        settings.set('theme', theme.mode())  # Migrate removed/unknown themes to Obsidian Gold.
    user_accent = settings.get('accent', '#4f8cff')
    from . import wallpaper_accents
    effective_accent = wallpaper_accents.effective_selection(user_accent)
    if effective_accent != user_accent:
        settings.set('accent', effective_accent)
    theme.set_accent('#4f8cff' if eco.enabled() else resolve_accent(effective_accent, info['color']))
    app.setStyleSheet(theme.stylesheet())
    logo = load_logo(info, 96)
    app.setWindowIcon(app_icon())
    from .brand import sync_installed_icon
    sync_installed_icon()
    def ready(win,manager):
        if os.environ.get('VITALUX_LOCAL_PREVIEW')=='1':win.setWindowTitle('Vitalux · Design Preview · '+theme.mode().replace('_',' ').title())
        print(f"Vitalux: Fensterplattform={app.platformName()}, Grafik-Backend={win.render_backend_active}, Fenstergröße={win.width()}x{win.height()} logisch",flush=True)
        QTimer.singleShot(4500,renderer.successful_start)
        if renderer.warning():win.statusBar().showMessage(renderer.warning(),16000)
        QTimer.singleShot(0,manager.check)
        from .guide import offer_first_start_guide
        QTimer.singleShot(1800,lambda:offer_first_start_guide(win))
    from .startup import StartupController
    app.startup=StartupController(app,info,logo,instance,ready)
    result = app.exec()
    win=app.startup.window
    if result == 0 and win is not None and win.restart_requested:
        renderer.successful_start()
        result=42  # The portable launcher restarts after native GUI disposal.
    from .lifecycle import dispose_gui
    dispose_gui(app.startup)
    sys.exit(result)


if __name__ == "__main__":
    main()
