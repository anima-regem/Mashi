"""Keep exceptions from a native file chooser inside the desktop boundary."""

import logging

LOG = logging.getLogger(__name__)


def guarded_file_picker(original, notify):
    """Complete a WebKit selection once, including when its Python delegate fails."""
    def guarded(delegate, webview, parameters, frame, completion):
        completed = False

        def finish(files):
            nonlocal completed
            if completed:
                return
            completed = True
            completion(files)

        try:
            return original(delegate, webview, parameters, frame, finish)
        except Exception:
            # Python exceptions crossing this Objective-C callback can abort Cocoa.
            LOG.exception("Native file picker failed; selection cancelled")
            try:
                finish(None)
            except Exception:
                LOG.exception("Native file picker cancellation failed")
            try:
                notify()
            except Exception:
                LOG.exception("Native file picker error notice failed")

    guarded._mashi_picker_guard = True
    return guarded


def install_file_picker_guard(cocoa, objc, notify):
    """Guard the pinned pywebview delegate without editing the installed package."""
    delegate = cocoa.BrowserView.BrowserDelegate
    method = delegate.webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_
    original = method.callable
    if getattr(original, "_mashi_picker_guard", False):
        return
    if not callable(original):
        raise RuntimeError("The native file chooser is incompatible with this desktop build")
    wrapped = guarded_file_picker(original, notify)
    # Retain the native block signature; call the saved Python implementation,
    # rather than dispatching the replaced Objective-C selector recursively.
    objc.classAddMethods(delegate, [
        objc.selector(wrapped, selector=method.selector, signature=method.signature),
    ])
