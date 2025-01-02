from os.path import (join, exists)
from os import (makedirs)

INPUT_FOLDER = "data"
OUTPUT_FOLDER = "outputs"
KNOWN_FILES = "FileNames.json"
FOUND_FILES = "FoundFiles.json"

ADGC_OUTPUT = "AdGCForms"
RAW_OUTPUT = "Raw files"
REFERENCED_OUTPUT = "Referenced files"
UNREFERENCED_CMPR_OUTPUT = "Unreferenced files"

REL_OUTPUT = "Rels"

MSSB_CODE_FILE = "aaaa.dat"
MSSB_DATA_FILE = "ZZZZ.dat"

FS03_CODE_FILE = "fqp.dat"
FS03_DATA_FILE = "fq.dat"

MAIN_DOL = "main.dol"

VERSIONS = [
    "US",
    "JP",
    "EU",
    "DEMO",
    "FS03",
]

class FilePaths:
    def __init__(self, version:str) -> None:
        self.version = version

        self.version_input_folder = join(INPUT_FOLDER, version)

        self.output_folder = join(OUTPUT_FOLDER, version)

        self.set_code_file_name(MSSB_CODE_FILE)
        self.set_data_file_name(MSSB_DATA_FILE)
        self.set_main_file_name(MAIN_DOL)

        self.known_files_path = join(self.version_input_folder, KNOWN_FILES)
        self.found_files_path = join(self.output_folder, FOUND_FILES)

        self.output_adgc = join(self.output_folder, ADGC_OUTPUT)
        self.output_raw = join(self.output_folder, RAW_OUTPUT)
        self.output_compressed_referenced = join(self.output_folder, REFERENCED_OUTPUT)
        self.output_compressed_unreferenced = join(self.output_folder, UNREFERENCED_CMPR_OUTPUT)
        self.output_rels = join(self.output_folder, REL_OUTPUT)

    def set_code_file_name(self, code_file_name:str):
        self._code_file_name = code_file_name
        self.code_path = join(self.version_input_folder, self._code_file_name)

    def set_data_file_name(self, data_file_name:str):
        self._data_file_name = data_file_name
        self.data_path = join(self.version_input_folder, self._data_file_name)

    def set_main_file_name(self, main_file_name:str):
        self._main_file_name = main_file_name
        self.main_path = join(self.version_input_folder, self._main_file_name)

    def valid(self):
        return all([
            exists(self.code_path),
            exists(self.data_path),
            exists(self.main_path),
        ])

    def extracted(self):
        return exists(self.found_files_path)

VERSION_PATHS = {
    v: FilePaths(v) for v in VERSIONS
}

# fs03 is the only game that uses different file naming conventions
VERSION_PATHS["FS03"].set_data_file_name(FS03_DATA_FILE)
VERSION_PATHS["FS03"].set_code_file_name(FS03_CODE_FILE)

def ensure_dir(path:str):
    makedirs(path, exist_ok=True)

def get_parts_of_file(file_bytes:bytes):
    found_inds = []

    i = 0
    while True:
        new_ind = int.from_bytes(file_bytes[i:i+4], 'big')
        i += 4

        if new_ind == 0:
            break

        if len(found_inds) != 0 and new_ind <= found_inds[-1]:
            break

        found_inds.append(new_ind)

    return found_inds

class FileCache:
    def __init__(self) -> None:
        self.__byte_cache__: dict[str, bytes] = {}

    def __cache_file(self, file_name:str):
        if file_name not in self.__byte_cache__:
            with open(file_name, "rb") as f:
                self.__byte_cache__[file_name] = f.read()

    def get_file_bytes(self, file_name:str)->bytes:
        with open(file_name, "rb") as f:
            return f.read()

        # self.__cache_file(file_name)
        # return self.__byte_cache__[file_name]

FILE_CACHE = FileCache()
