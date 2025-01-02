from typing import Any


class MssbAssetLog():
    LOG_CALLBACK = lambda *args, **kwargs: None

    def __init__(self, label_callback = None, progbar_callback=None, max_iterations=-1) -> None:
        self.label_callback = self.LOG_CALLBACK
        self.progress_bar_callback = progbar_callback
        self.max_iter = max_iterations

    def update_label(self, *args, **kwargs):
        if self.label_callback:
            self.label_callback(*args, **kwargs)

    def update_iters(self, iters):
        if self.progress_bar_callback:
            if self.max_iter == 0:
                self.progress_bar_callback(0)
            else:
                self.progress_bar_callback(iters / self.max_iter)

    def set_max_iters(self, max_iters):
        self.max_iter = max_iters
    
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        if self.LOG_CALLBACK:
            print(*args, *kwds)
            self.LOG_CALLBACK(*args, **kwds)
    def finish(self):
        self.update_iters(self.max_iter)
        self.update_label("Done")
    
    def __str__(self) -> str:
        return "MssbAssetLog: "
