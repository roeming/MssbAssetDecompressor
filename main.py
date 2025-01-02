import json
import dearpygui.dearpygui as dpg
from dearpygui_ext import logger
from libraries.MssbAssetSearcher.log_callback import MssbAssetLog
from libraries.MssbAssetSearcher.search import populate_outputs
from libraries.MssbAssetSearcher.helper_filesystem import VERSION_PATHS, join
import io
import threading
from os.path import exists

class SharedObject:
    def __init__(self, value=None) -> None:
        self.value = value

    def __call__(self, *args, **kwds):
        return self.value
    
class ButtonLock:
    def __init__(self, tag):
        self.tag = tag

    def __enter__(self):
        dpg.disable_item(self.tag)
        return self

    def __exit__(self, *args):
        dpg.enable_item(self.tag)

def print_args_to_string(*args, **kwargs):
    with io.StringIO() as output:
        print(*args, file=output, **kwargs)
        return output.getvalue()

stopExtractionObj = SharedObject()
def extraction_progbar(sender, app_data, user_data):
    global stopExtractionObj

    def _extract():
        with ButtonLock(sender):
            
            stopExtractionObj.value = False

            (tag_progbar, tag_label, tag_window, callable_action, name, skip_if_extracted) = user_data
            dpg.show_item(tag_window)
            dpg.set_item_label(tag_window, name)

            l = MssbAssetLog()
            l.progress_bar_callback = lambda val: dpg.set_value(tag_progbar, value=val)
            l.label_callback = lambda *args, **kwargs: dpg.set_value(tag_label, value=print_args_to_string(*args, **kwargs))

            callable_action(l, skip_if_extracted, stopExtractionObj)

            dpg.hide_item(tag_window)
        update_visibility_on_assets()
    
    threading.Thread(target=_extract, args=(), daemon=True).start()

def stopExtraction(sender, app_data, user_data):
    global stopExtractionObj
    stopExtractionObj.value = True

def open_hex_view(path):
    from construct_editor.wx_widgets import WxHexEditor
    import wx
    def _open_hex_view():

        if not exists(path):
            return
        
        with open(path, "rb") as f:
            b = f.read()

        app = wx.App(False)
        frame = wx.Frame(None, title=path, size=(500, 500))
        
        editor_panel = WxHexEditor(frame, binary=b)
        frame.Show(True)
        app.MainLoop()
    _open_hex_view()
    # threading.Thread(target=_open_hex_view, args=(), daemon=True).start()

def populate_asset_viewer():
    MssbAssetLog("Populating assets...")
    parent_tag = "asset_view"

    def strike(text):
        return f"~~{text}~~"

    # get rid of children

    children = dpg.get_item_children(parent_tag)
    if children:
        MssbAssetLog("Found old asset list, deleting...")

        tree_child_container_id = 1
        for asset in children[tree_child_container_id]:
            dpg.delete_item(asset)

    for v in VERSION_PATHS.values():
        if not v.extracted():
            MssbAssetLog(f"Didn't find assets for {v.version} version, skipping")
            continue

        MssbAssetLog(f"Attempting to read extracted files for {v.version}...")
        with open(v.found_files_path, "r") as f:
            this_found_files = json.load(f)
            this_found_files:dict[str, list[dict]]
        
        # create folder tree items (US, JP, EU, ...)
        with dpg.tree_node(parent=parent_tag, label=v.version):

            # iterate over asset found types 
            for folder_name, assets in this_found_files.items():
                # sort by assets by appearence offset, so maybe similar files appear as neighbors?
                assets.sort(key=lambda x: x["offset"])

                # create folder view for asset type (Referenced Uncompressed, Compressed, etc...)
                with dpg.tree_node(label=folder_name):
                    for asset in assets:
                        with dpg.tree_node(label=asset["Output"]):
                            
                            file_name = asset["Output"]
                            asset_folder_path = join(v.output_folder, folder_name, file_name, file_name)                           

                            if not exists(asset_folder_path):
                                file_name = strike(file_name)

                            dpg.add_menu_item(
                                label=file_name,
                                user_data=asset_folder_path,
                                callback=lambda sender, app_data, user_data: open_hex_view(user_data)
                            )

def should_show_asset_buttons():
    all_extracted = [x.extracted() for x in VERSION_PATHS.values() if x.valid()]
    # if any asset has been extracted, go ahead and show the buttons to work with
    return any(all_extracted)

disabled_items_if_no_assets = []
def update_visibility_on_assets():
    global disabled_items_if_no_assets
        
    enabled_assets = should_show_asset_buttons()

    for x in disabled_items_if_no_assets:
        if enabled_assets:
            dpg.show_item(x) 
        else:
            dpg.hide_item(x)

    populate_asset_viewer()

def main():
    dpg.create_context()

    my_logger_window = logger.mvLogger()
    dpg.set_item_pos(my_logger_window.window_id, (100,0))
    
    MssbAssetLog.LOG_CALLBACK = lambda *args, **kwargs: my_logger_window.log_info(print_args_to_string(*args, **kwargs))

    with dpg.window(width=250, show=False, no_close=True, no_collapse=True) as progress_bar_tag:
        tag_progbar_bar = dpg.add_progress_bar()
        tag_progbar_label = dpg.add_text()
        tag_cancel_button = dpg.add_button(label="Cancel", callback=stopExtraction)

    with dpg.window(label="Asset View", tag="asset_view_window", show=False, no_close=True, width=280, height=400):
        dpg.add_button()
        with dpg.group(tag="asset_view"):
            pass

    with dpg.window(label="main window", no_close=True, width=200, height=150):

        tag_all_assets = dpg.add_button(
            label="Extract All Assets", 
            user_data=(tag_progbar_bar, tag_progbar_label, progress_bar_tag, populate_outputs, "Extraction Search", True), 
            callback=extraction_progbar
        )

        tag_new_assets = dpg.add_button(
            label="Extract Only New Assets", 
            user_data=(tag_progbar_bar, tag_progbar_label, progress_bar_tag, populate_outputs, "Extraction Search", False), 
            callback=extraction_progbar
        )

        tag_show_heirarchy = dpg.add_button(
            label="Show Asset Heirarchy", 
            callback=lambda *args: dpg.show_item("asset_view_window")
        )

        dpg.add_button(
            label="Show Log",
            callback=lambda *args: dpg.show_item(my_logger_window.window_id)
        )

        disabled_items_if_no_assets.extend([tag_show_heirarchy, tag_new_assets])
        update_visibility_on_assets()

    dpg.create_viewport(title='Mssb Asset Searcher', width=800, height=600)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__": main()

