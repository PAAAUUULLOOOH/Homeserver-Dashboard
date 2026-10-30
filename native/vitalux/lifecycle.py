"""Finish optional product work and dispose native widgets while Qt is alive."""
from PySide6.QtCore import QAbstractAnimation,QCoreApplication,QEvent,QTimer
from PySide6.QtWidgets import QApplication


def product_workers():
    app=QApplication.instance()
    return [worker for name in ('_product_image_loader','_spec_loader')
            if (worker:=getattr(app,name,None)) is not None]


def stop_product_workers():
    # Request every cancellation even if a previous pool still has work.
    states=[worker.shutdown() for worker in product_workers()]
    return all(states)


def resume_product_workers():
    for worker in product_workers():worker.resume()


def stop_gui_activity(window):
    for animation in window.findChildren(QAbstractAnimation):animation.stop()
    for timer in window.findChildren(QTimer):timer.stop()
    window.setUpdatesEnabled(False)


def dispose_gui(controller):
    """Destroy windows before interpreter/module teardown destroys Qt resources."""
    import shiboken6
    controller.worker.requestInterruption()
    controller.worker.wait()
    stop_product_workers()
    for worker in product_workers():worker.pool.waitForDone()
    window=controller.window
    if window is not None and shiboken6.isValid(window):
        window.sampler.stop();window.sampler.wait()
        stop_gui_activity(window)
        # Dialogs, tool windows and the scene are owned by the main window.
        # The independent MiniHUD must also die before QApplication.
        hud=getattr(window,'_mini_hud',None)
        if hud is not None and shiboken6.isValid(hud):shiboken6.delete(hud)
        shiboken6.delete(window)
    if shiboken6.isValid(controller.splash):
        stop_gui_activity(controller.splash)
        controller.splash.ready=True;controller.splash.close()
        shiboken6.delete(controller.splash)
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
