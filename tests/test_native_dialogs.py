import pytest

from mashi.native_dialogs import guarded_file_picker


@pytest.mark.parametrize("files", [None, ["synthetic.png"]])
def test_success_and_user_cancel_keep_the_original_result(files):
    results, notices = [], []

    def original(delegate, webview, parameters, frame, completion):
        completion(files)
        return "finished"

    guarded = guarded_file_picker(original, lambda: notices.append("error"))
    assert guarded(None, None, None, None, results.append) == "finished"
    assert results == [files] and not notices


def test_delegate_exception_cancels_and_reports_without_escaping(caplog):
    results, notices = [], []

    def broken(*args):
        raise RuntimeError("synthetic chooser failure")

    guarded = guarded_file_picker(broken, lambda: notices.append("error"))
    assert guarded(None, None, None, None, results.append) is None
    assert results == [None] and notices == ["error"]
    assert "Native file picker failed; selection cancelled" in caplog.text


def test_late_delegate_failure_never_completes_a_selection_twice():
    results, notices = [], []

    def broken(delegate, webview, parameters, frame, completion):
        completion(["synthetic.png"])
        raise RuntimeError("failure after completion")

    guarded = guarded_file_picker(broken, lambda: notices.append("error"))
    guarded(None, None, None, None, results.append)
    assert results == [["synthetic.png"]] and notices == ["error"]


def test_failing_completion_and_notice_do_not_escape_the_cocoa_callback(caplog):
    calls = []

    def broken(*args):
        raise RuntimeError("synthetic chooser failure")

    def complete(value):
        calls.append(value)
        raise RuntimeError("synthetic completion failure")

    def notice():
        raise RuntimeError("synthetic notice failure")

    guarded_file_picker(broken, notice)(None, None, None, None, complete)
    assert calls == [None]
    assert "Native file picker cancellation failed" in caplog.text
    assert "Native file picker error notice failed" in caplog.text
