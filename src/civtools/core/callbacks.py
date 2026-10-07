"""Plain Python callbacks keep engineering services independent of any UI toolkit."""
class MessageKinds:
    showinfo = "info"
    showwarning = "warning"
    showerror = "error"


class ServiceCallbacks:
    def __init__(self, report):
        self.report = report
        self.errors = []
        self.result = None
        self.workbook = None

    def log_message(self, message, level="INFO", status=None):
        self.report("log", str(message))

    def log_error(self, message):
        self.errors.append(str(message))
        self.report("log", f"Error: {message}")

    def log_success(self, message):
        self.result = str(message)
        self.report("log", str(message))

    def update_progress(self, value):
        self.report("progress", round(value * 100))

    def _set_process_status(self, **kwargs):
        self.report("stage", kwargs.get("text", ""))

    def _set_progress(self, method, *args, **kwargs):
        if method == "set":
            self.update_progress(args[0])

    def _show_message(self, kind, title, message):
        if kind in (MessageKinds.showerror, MessageKinds.showwarning):
            self.log_error(message)
        else:
            self.result = str(message)

    def _enable_buttons(self):
        if self.workbook is not None:
            self.workbook.close()
            self.workbook = None

    def after(self, delay, callback, *args):
        # Services run wholly in a worker; reporting is done through Qt signals.
        callback(*args)

    def _finish_plot(self, result_message=None, error_title=None, error_message=None):
        if error_title:
            self.log_error(error_message)
        else:
            self.result = result_message

    def finish(self):
        if self.errors:
            raise RuntimeError("\n".join(self.errors))
        if not self.result:
            raise RuntimeError("No changes were completed. Review the operation log.")
        return self.result
