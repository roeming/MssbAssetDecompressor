from __future__ import annotations
import json
import json.encoder
from .helper_filesystem import (FilePaths, VERSION_PATHS, exists, ensure_dir, join, FILE_CACHE, REFERENCED_OUTPUT, ADGC_OUTPUT, UNREFERENCED_CMPR_OUTPUT, RAW_OUTPUT, REL_OUTPUT)
import construct as cs
from .lzss import (get_compressed_size, get_decompressed_size, test_decompress, decompress, BitBufferReadException, IllegalDecompressionSequenceException, LZ11_BITS_PER_LOOKBACK, LZ11_BITS_PER_REPETITION)
from .MultipleRanges import MultipleRanges
from .log_callback import MssbAssetLog


class DataEntry():
    COMPRESSION_CONSTRUCT = cs.BitStruct(
        cs.Const(0, cs.BitsInteger(16)),
        "repetition_bit" / cs.BitsInteger(8),
        "lookback_bit" / cs.BitsInteger(8),
        "compression_flag" / cs.BitsInteger(4),
        "original_size" / cs.BitsInteger(28),
        "offset" / cs.BitsInteger(32),
        "compressed_size" / cs.BitsInteger(32),
    )

    SIZE = COMPRESSION_CONSTRUCT.sizeof()

    def __init__(self, b: type[bytes | dict], offset:int=0, file="") -> None:
        output_name = None
        if isinstance(b, dict):
            output_name = b.get("Output", None)
            file = b.get("Input")
            b = self.COMPRESSION_CONSTRUCT.build(b) # kinda unneccessary, but whatever
            # makes it easy to parse
        parsed = self.COMPRESSION_CONSTRUCT.parse(b[offset : offset + self.SIZE])

        self.repetition_bit_size = parsed.repetition_bit
        self.lookback_bit_size = parsed.lookback_bit
        self.compression_flag = parsed.compression_flag
        self.original_size = parsed.original_size
        self.disk_location = parsed.offset
        self.compressed_size = parsed.compressed_size
        self.file = file
        if output_name != None:
            self.output_name = output_name
        else:
            self.reset_output_name()

    def reset_output_name(self):
        self.output_name = f"{self.lookback_bit_size:02x}{self.repetition_bit_size:02x} {self.disk_location:08x}.dat"

    @property
    def footer_size(self):
        base = 0x800
        size = self.disk_location + self.compressed_size
        size %= base
        if size == 0:
            footer = 0
        else:
            footer = base - size

        return footer

    def __str__(self) -> str:
        return (
        f'File:            {self.file}\n'
        f'Output Name:     {self.output_name}\n'
        f'Lookback bits:   0x{self.lookback_bit_size:02x}\n'
        f'Repetition bits: 0x{self.repetition_bit_size:02x}\n'
        f'Original Size:   0x{self.original_size:x}\n'
        f'Disk Location:   0x{self.disk_location:08x}\n'
        f'Compressed Size: 0x{self.compressed_size:x}\n'
        f'Compressed Flag: {self.compression_flag}\n'
        f'Footer Size:     0x{self.footer_size:x}'
        )

    def to_dict(self)->dict:
        return {
            "Input": self.file,
            "Output": self.output_name,
            "lookback_bit": self.lookback_bit_size,
            "repetition_bit": self.repetition_bit_size,
            "original_size": self.original_size,
            "offset": self.disk_location,
            "compressed_size": self.compressed_size,
            "compression_flag": self.compression_flag,
            "footerSize": self.footer_size
        }

    def from_dict(d:dict) -> DataEntry:
        return DataEntry(d)

    def to_range(self) -> range:
        return range(self.disk_location, self.disk_location + self.compressed_size + self.footer_size)

    def __hash__(self) -> int:
        return hash((self.file, self.lookback_bit_size, self.repetition_bit_size, self.original_size, self.disk_location, self.compressed_size, self.compression_flag, self.footer_size))

    def equals_besides_filename(self, __o: object):
        if not isinstance(__o, DataEntry):
            return False

        return self.lookback_bit_size == __o.lookback_bit_size and self.repetition_bit_size == __o.repetition_bit_size and self.original_size == __o.original_size and self.disk_location == __o.disk_location and self.compressed_size == __o.compressed_size and self.compression_flag == __o.compression_flag and self.footer_size == __o.footer_size

    def __eq__(self, __o: object) -> bool:
        return self.equals_besides_filename(__o) and self.file == __o.file

    def __lt__(self, __o: object):
        if not isinstance(__o, DataEntry):
            return False
        return self.disk_location < __o.disk_location

    def __repr__(self) -> str:
        return self.__str__()

class FingerPrintSearcher:
    USABLE_CMPR_CONSTANTS = ((11, 4), (0xe, 5))

    def search_all_compressions(self, data:bytes, asset_file_name:str) -> set[DataEntry]:
        s = set()
        for lookback, repetition in self.USABLE_CMPR_CONSTANTS:
            s.update(self.search_compression(data, lookback, repetition, asset_file_name))
        return s

    def search_compression(self, data:bytes, lookback:int, repetitions:int, asset_file_name:str) -> set[DataEntry]:
        to_find = bytes([0, 0, repetitions, lookback])
        fingerprint_size = len(to_find)
        data_size = len(data)

        found = set()
        begin_index = 0
        ind = data.find(to_find, begin_index)
        while ind > 0 and ind + DataEntry.SIZE <= data_size:
            entry = DataEntry(data, ind, asset_file_name)
            # for now it has to be a mult of 2048 bytes, and not 0
            if entry.disk_location % 0x800 == 0 and entry.disk_location != 0 and entry.compression_flag == 4:
                found.add(entry)

            # increment to found index + 4 (compression fingerprintSize)
            # could be 16 (size of DataEntry) if found, but its best to get lots of data, and test each one
            begin_index = ind + fingerprint_size

            ind = data.find(to_find, begin_index)

        return found

    def search_uncompressed(self, data:bytes, asset_file_name:str) -> set[DataEntry]:
        epsilon = 3
        to_find = (0).to_bytes(4, 'big')
        data_size = len(data)

        found = set()
        begin_index = 0
        ind = data.find(to_find, begin_index)
        while ind > 0 and ind + DataEntry.SIZE <= data_size:
            entry = DataEntry(data, ind, asset_file_name)
            # for now it has to be a mult of 2048 bytes, not 0, and no compression flag
            if (entry.compression_flag == 0 and entry.disk_location % 0x800 == 0 and entry.disk_location != 0 and
                # compressed size and entry size should be close to same size, but not 0
                entry.compressed_size > 0 and entry.original_size > 0 and abs(entry.compressed_size - entry.original_size) <= epsilon):
                found.add(entry)

            begin_index = ind + 1
            ind = data.find(to_find, begin_index)
        return found

    def search_adgc(self, data:bytes, asset_file_name:str) -> set[DataEntry]:
        to_find = b"AdGCForm"
        data_size = len(data)
        import struct

        found = set()
        begin_index = 0
        ind = data.find(to_find, begin_index)
        while ind > 0 and ind + DataEntry.SIZE <= data_size:
            compression_beginning = ind + len(b"AdGCForm")
            finger_print = data[ind-8:ind]

            original_size, compression_info = struct.unpack('<II', finger_print)
            compressed_flag = original_size >> 28
            original_size &= 0xfffffff

            if compressed_flag == 0:
                lookback_bit = 0
                repetition_bit = 0
                compressed_size = original_size
            else:
                lookback_bit = compression_info & 0xff
                repetition_bit = (compression_info >> 8) & 0xff

                compressed_size = get_compressed_size(data, compression_beginning, original_size, lookback_bit, repetition_bit)

            entry = DataEntry.from_dict({
                "Input": asset_file_name,
                "Output":  f"AdGCForm {lookback_bit:02x}{repetition_bit:02x} {compression_beginning:08x}.dat",
                "lookback_bit" : lookback_bit,
                "repetition_bit": repetition_bit,
                "original_size" : original_size,
                "offset" : compression_beginning,
                "compressed_size" : compressed_size,
                "compression_flag" : compressed_flag
            })

            found.add(entry)

            begin_index = ind + 1
            ind = data.find(to_find, begin_index)
        return found

    def get_code_files(self, data:bytes, found_main_compressions:set[DataEntry], code_file_name:str) -> set[DataEntry]:
        found = []

        minimum_bytes_to_decompress = 200
        lookback = 11
        repetition = 4

        found_code_decompressions = [
            offset
            for offset
            in range(0, len(data), 0x800)
            if test_decompress(data, offset, minimum_bytes_to_decompress, lookback, repetition)
        ]

        for this_offset in found_code_decompressions:
            matches = [x for x in found_main_compressions if x.disk_location == this_offset]

            # I'm confident this works, don't need to check
            # assert(len(matches) in [0,1]), f"{matches}"

            for m in matches:
                # make sure the match actually works
                if test_decompress(data, m.disk_location, m.original_size, m.lookback_bit_size, m.repetition_bit_size):
                    # remove the fingerprint from the list of found fingerprints
                    found_main_compressions.remove(m)
                    # copy the data entry, but make sure to change the input file
                    v = DataEntry.from_dict(m.to_dict() | {"Input" : code_file_name})
                    found.append(v)

        return set(found)

    def find_unreferenced_compressed_files(self, data: bytes, already_found_compressed_files: set[DataEntry], data_file_name:str):
        minimum_bytes_to_decompress = 200

        found = []
        multi_range = MultipleRanges()

        for cmpr_files in already_found_compressed_files:
            multi_range.add_range(cmpr_files.to_range())

        for lookback, repetition in self.USABLE_CMPR_CONSTANTS:
            for offset in range(0, len(data), 0x800):
                if offset not in multi_range and test_decompress(data, offset, minimum_bytes_to_decompress, lookback, repetition):
                    found.append((offset, lookback, repetition))

            for f in found:
                multi_range.add_range(range(f[0], f[0] + minimum_bytes_to_decompress))

        out = [
            DataEntry.from_dict({
                "Input": data_file_name,
                "Output":  f"{lookback:02x}{repetition:02x} {offset:08x}.dat",
                "lookback_bit" : lookback,
                "repetition_bit": repetition,
                "original_size" : 0,
                "offset" : offset,
                "compressed_size" : 0,
                "compression_flag" : 4
            })
            for offset, lookback, repetition
            in found
        ]

        return set(out)


def populate_outputs(log_callback:MssbAssetLog, skip_if_extracted, stopExtracting):

    for i, version_paths in enumerate(VERSION_PATHS.values()):
        if stopExtracting():
            break
        log_callback.set_max_iters(len(VERSION_PATHS))
        if not version_paths.extracted() or skip_if_extracted:
            log_callback.update_iters(i)
            log_callback.update_label(f"Checking {version_paths.version} version...")
            search_game(version_paths, log_callback, stopExtracting)
        else:
            log_callback(f"{version_paths.version} already extracted, skipping...")

    log_callback.finish()


def look_for_missing_ranges(multiRange:MultipleRanges, data:bytes, data_file_name:str):
    upper_segment_start = p = len(data)
    prev_p = p
    SEGMENT_SIZE = 0x800
    
    min_bytes_to_decompress = 0x200

    # round down to nearest 0x800

    if p % SEGMENT_SIZE != 0:
        p -= p % SEGMENT_SIZE

    out = []
    
    # start by marking "are we in an asset"
    found_decompression = p in multiRange
    just_wrote_a_segment = False
    # p will be walking backwards
    # if ever p finds itself inside a known range, we move prev_segment_start to p
    # if ever p finds itself outside a known range, we can attempt up to prev_segment_start
    while p >= 0:
        wrote_a_segment_this_loop = False
        # If we are in the range, then either we've been here for a while, or we just got into the range

        if p in multiRange:
            been_in_the_range_for_a_while = (prev_p == upper_segment_start)
            if (not been_in_the_range_for_a_while  # if we just entered the range
                    and not just_wrote_a_segment): # if we just wrote an entry, no need to write another, we probably just started an entry 
                # time to write a raw entry, because we just entered the range
                out.append(DataEntry.from_dict({
                    "Input": data_file_name,
                    "Output":  f"{0:02x}{0:02x} {prev_p:08x}.dat",
                    "lookback_bit" : 0,
                    "repetition_bit": 0,
                    "original_size" : upper_segment_start - prev_p,
                    "offset" : p,
                    "compressed_size" : upper_segment_start - prev_p,
                    "compression_flag" : 0
                }))
                wrote_a_segment_this_loop = True
            # drag the upper segment along with us
            upper_segment_start = p

        in_the_range_now = (p == upper_segment_start)

        # if ever we are in a section that is not in a range, look to decompress
        if not in_the_range_now and test_decompress(data, p, min_bytes_to_decompress):
            # we found a range that can be decompressed, assume it goes all the way to the end of this section
            out.append(DataEntry.from_dict({
                "Input": data_file_name,
                "Output":  f"{LZ11_BITS_PER_LOOKBACK:02x}{LZ11_BITS_PER_REPETITION:02x} {p:08x}.dat",
                "lookback_bit" : LZ11_BITS_PER_LOOKBACK,
                "repetition_bit": LZ11_BITS_PER_REPETITION,
                "original_size" : get_decompressed_size(data, p, upper_segment_start - p),
                "offset" : p,
                "compressed_size" : upper_segment_start - p,
                "compression_flag" : 4
            }))
            # drag the upper section to be this section that we just wrote
            upper_segment_start = p

            wrote_a_segment_this_loop = True

        just_wrote_a_segment = wrote_a_segment_this_loop
        prev_p = p
        p -= SEGMENT_SIZE

    return set(out)

def search_game(version_path : FilePaths, log_callback: MssbAssetLog, stopExtracting):
    log_callback(version_path.version)
    if not version_path.valid():
        # we can't read the main/data/code, so we can't decompress them
        log_callback("couldn't find relevant files, skipping")
        return

    ensure_dir(version_path.output_folder)

    cached_bytes = {
        x: FILE_CACHE.get_file_bytes(x)
        for x
        in [version_path.data_path, version_path.code_path, version_path.main_path]
    }

    this_data = cached_bytes[version_path.data_path]
    this_code = cached_bytes[version_path.code_path]
    this_main = cached_bytes[version_path.main_path]

    known_files = {}
    if exists(version_path.known_files_path):
        with open(version_path.known_files_path, "r") as f:
            file_offset_list = json.load(f)
        for d in file_offset_list:
            known_files[int(d["Location"], 16)] = d["Name"]

    # search for decompression fingerprints
    searcher = FingerPrintSearcher()
    found_compressed:set[DataEntry] = set()
    found_uncompressed:set[DataEntry] = set()
    found_rels:set[DataEntry] = set()
    found_adgc:set[DataEntry] = set()
    found_unreferenced:set[DataEntry] = set()

    def update_findings_from_code(code_data:bytes, compressed_set:set[DataEntry], uncompressed_set:set[DataEntry]):
        # work through main, find all compressed and uncompressed fingerprints
        found = searcher.search_all_compressions(code_data, version_path.data_path)
        if len(found) > 0:
            log_callback("found fingerprints", len(found))
        compressed_set.update(found)

        found = searcher.search_uncompressed(code_data, version_path.data_path)
        uncompressed_set.update(found)
        log_callback("found uncompressed", len(found))

    update_findings_from_code(this_main, found_compressed, found_uncompressed)
    if stopExtracting(): return

    # find the rels
    found_rels.update(searcher.get_code_files(this_code, found_compressed, version_path.code_path))
    log_callback("Found rels", len(found_rels))

    # find any adgc files
    found_adgc.update(searcher.search_adgc(this_data, version_path.data_path))
    log_callback("AdGC", len(found_adgc))
    if stopExtracting(): return

    for rel in found_rels:
        log_callback(f"{rel.disk_location:08x}")
        decompressed_rel = decompress(this_code, rel.disk_location, rel.original_size, rel.lookback_bit_size, rel.repetition_bit_size)
        update_findings_from_code(decompressed_rel, found_compressed, found_uncompressed)
        if stopExtracting(): return

    # found_unreferenced = searcher.find_unreferenced_compressed_files(this_data, found_compressed, version_path.data_path)
    
    multirange = MultipleRanges()
    for collection in (found_compressed, found_uncompressed, found_adgc):
        for entry in collection:
            multirange.add_range(entry.to_range())
    log_callback("looking for unreferenced files... (could take a minute)")
    _found_unreferenced = look_for_missing_ranges(multirange, this_data, version_path.data_path)
    log_callback("unreferenced", len(_found_unreferenced))
    found_unreferenced.update(_found_unreferenced)
    if stopExtracting(): return

    # time to attempt some decompressions
    log_callback("Validating all compressions")

    for folder, collection in [
            (version_path.output_compressed_referenced, found_compressed),
            (version_path.output_raw, found_uncompressed),
            (version_path.output_rels, found_rels),
            (version_path.output_adgc, found_adgc),
            (version_path.output_compressed_unreferenced, found_unreferenced)
        ]:
        collection_copy = list(collection)
        log_callback(f"Extracting {folder} files")
        
        log_callback.set_max_iters(len(collection_copy))
        for i, entry in enumerate(collection_copy):
            log_callback.update_label(f"Extracting {version_path.version} files... {i}/{len(collection_copy)}")
            if stopExtracting(): return

            entry:DataEntry
            log_callback.update_iters(i)
            data_to_extract = cached_bytes[entry.file]

            if entry.original_size > 0:
                if entry.compression_flag == 4:
                    try:
                        out_data = decompress(data_to_extract, entry.disk_location, entry.original_size, entry.lookback_bit_size, entry.repetition_bit_size)
                    except (BitBufferReadException, IllegalDecompressionSequenceException):
                        collection.remove(entry)
                        continue
                else:
                    out_data = data_to_extract[entry.disk_location : entry.disk_location + entry.original_size]
                
                # rename based on known file names
                if entry.file != version_path.code_path and entry.disk_location in known_files:
                    entry.output_name = known_files[entry.disk_location]

                this_output_folder = join(folder, entry.output_name)
                ensure_dir(this_output_folder)
                out_filename = join(this_output_folder, entry.output_name)

                with open(out_filename, "wb") as f:
                    f.write(out_data)


    def to_dict_list(data_entries: set[DataEntry]):
        return [
            x.to_dict()
            for x
            in data_entries
        ]
    out_json = {
        REL_OUTPUT: to_dict_list(found_rels),
        RAW_OUTPUT: to_dict_list(found_uncompressed),
        REFERENCED_OUTPUT: to_dict_list(found_compressed),
        ADGC_OUTPUT: to_dict_list(found_adgc),
        UNREFERENCED_CMPR_OUTPUT: to_dict_list(found_unreferenced),
    }

    ensure_dir(version_path.output_folder)
    with open(version_path.found_files_path, "w") as f:
        json.dump(out_json, f)

    # search for uncompressed fingerprints
    # verify all fingerprints