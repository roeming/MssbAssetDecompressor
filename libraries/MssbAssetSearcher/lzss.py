from math import ceil

BITS_PER_BYTE = 8 
LZ11_BITS_PER_LOOKBACK = 11
LZ11_BITS_PER_REPETITION = 4
LZ11_BITS_PER_FLAG = 1

# how many bytes would we need for it to make more sense to write the values individually

def get_min_repetitions(lookback_size: int, reptition_size: int) -> int:
    return ceil( (lookback_size + reptition_size + LZ11_BITS_PER_FLAG) / (LZ11_BITS_PER_FLAG + BITS_PER_BYTE) )

LZ11_FLAG_REPETITION = 0
LZ11_FLAG_ORIGINAL = 1

def make_mask(bit_count:int): 
    return (1 << bit_count) - 1

class BitBufferReadException(Exception): pass

class bitbuffer:
    __BYTE_COUNT_PER_BUFFER = 4
    __BITS_PER_BUFFER = __BYTE_COUNT_PER_BUFFER * BITS_PER_BYTE
    __ENDIAN = "big"

    def __init__(self, data = bytearray(), offset = 0) -> None:
        self._byte_array = data
        self.bit_buffer = 0
        self.buffer_bit_count = 0
        self.byte_index = offset
    
    def __get_new_buffer_section(self) -> None:
        if self.byte_index + self.__BYTE_COUNT_PER_BUFFER > len(self._byte_array):
            raise BitBufferReadException("Ran out of bits in Bit buffer")
        self.bit_buffer         = int.from_bytes(self._byte_array[self.byte_index : self.byte_index + self.__BYTE_COUNT_PER_BUFFER], self.__ENDIAN)        
        self.byte_index         += self.__BYTE_COUNT_PER_BUFFER
        self.buffer_bit_count   = self.__BITS_PER_BUFFER

    def __write_new_buffer_section(self) -> None:
        self._byte_array.extend(int.to_bytes(self.bit_buffer, self.__BYTE_COUNT_PER_BUFFER, self.__ENDIAN))
        self.bit_buffer         = 0
        self.buffer_bit_count   = 0

    def read_bits(self, bit_count:int):
        output = 0
        # if we don't have enough bits in the buffer
        if self.buffer_bit_count < bit_count:

            # we have x amount of bits left in the buffer
            # so therefore we need count-x bits from the next int
            bit_count -= self.buffer_bit_count

            # the stuff left in the buffer absolutely is part of the value to be returned
            # make space at the bottom of the int for the new bits
            output = self.bit_buffer << bit_count
            
            # read in a new buffer
            self.__get_new_buffer_section()

            # dropping out of the `if`, we combine our old value with some new bits

        # return the bottom bits of the buffer
        output |= (self.bit_buffer & make_mask(bit_count))
        
        # cycle out the bits
        self.bit_buffer >>= bit_count
        self.buffer_bit_count -= bit_count

        return output
    
    def write_bits(self, val:int, bit_count:int):
        # just make sure we're using an int with a valid number of bits
        val &= make_mask(bit_count)

        # we will fill up our buffer
        if bit_count + self.buffer_bit_count >= self.__BITS_PER_BUFFER:
            # figure out how many bits we have left in the buffer
            space_left = self.__BITS_PER_BUFFER - self.buffer_bit_count

            bottom_bit_count = bit_count - space_left

            # we want to write the top bits into the end of the int
            top_bits = (val >> bottom_bit_count)

            # hold on to the lower bits
            lower_bits = val & make_mask(bottom_bit_count)

            # write top bits to top of buffer
            self.bit_buffer |= top_bits << self.buffer_bit_count

            # write out buffer
            self.__write_new_buffer_section()
            
            # write the new bits, recursive call to hit the `else` section
            self.write_bits(lower_bits, bottom_bit_count)
        
        else:
            # `or` in the new value, new values get shifted over further
            self.bit_buffer |= val << self.buffer_bit_count

            # count the bits into how full the buffer is
            self.buffer_bit_count += bit_count

    def to_bytes(self) -> bytes:
        # if we have bits in the buffer, they aren't in the final byte array
        if self.buffer_bit_count != 0:
            bits_left = self.__BITS_PER_BUFFER - self.buffer_bit_count
            # write 0s until the last buffer is added to the byte array
            self.write_bits(0, bits_left)

        # all data is in the array
        return bytes(self._byte_array)


class IllegalDecompressionSequenceException(Exception): pass

# only to be called if you know there exists a compression here
def get_decompressed_size(in_buffer: bytes, offset: int, compressed_size: int, lookback_size=LZ11_BITS_PER_LOOKBACK, repetition_size=LZ11_BITS_PER_REPETITION) -> int:
    
    COMPRESSED_DATA = bitbuffer(in_buffer[offset : offset + compressed_size]) # have a cut-off buffer to read from, therefore guarenteeing an exception

    min_reptition = get_min_repetitions(lookback_size, repetition_size)

    size_int = 0
    try:
        while True:
            if COMPRESSED_DATA.read_bits(LZ11_BITS_PER_FLAG) == LZ11_FLAG_REPETITION:

                # reading a lookback of 0 would look at the last item in the buffer
                lookback = COMPRESSED_DATA.read_bits(lookback_size)
                if lookback >= size_int:
                    # return as many as we read
                    return size_int

                size_int += COMPRESSED_DATA.read_bits(repetition_size) + min_reptition

            else: # LZ11_FLAG_ORIGINAL
                # consume 1 byte
                COMPRESSED_DATA.read_bits(BITS_PER_BYTE)
                size_int += 1            
    except BitBufferReadException:
        # if we attempted to read from the buffer, but there were no more bits in the buffer
        pass

    return size_int
     
def get_compressed_size(in_buffer: bytes, offset: int, final_decompressed_size: int, lookback_size=LZ11_BITS_PER_LOOKBACK, repetition_size=LZ11_BITS_PER_REPETITION) -> int:
    COMPRESSED_DATA = bitbuffer(in_buffer, offset)

    min_reptition = get_min_repetitions(lookback_size, repetition_size)
    # there's a size at which all data read will be valid, so as long as you have enough bytes in the buffer, you could technically go on forever
    # we can stop looking after that size 
    # max_size = min(2**lookback_size - 1, final_decompressed_size)
    max_size = final_decompressed_size

    size_int = 0
    try:
        while size_int < max_size:
            if COMPRESSED_DATA.read_bits(LZ11_BITS_PER_FLAG) == LZ11_FLAG_REPETITION:

                # reading a lookback of 0 would look at the last item in the buffer
                lookback = COMPRESSED_DATA.read_bits(lookback_size)
                if lookback >= size_int:
                    return -1

                size_int += COMPRESSED_DATA.read_bits(repetition_size) + min_reptition

            else: # LZ11_FLAG_ORIGINAL
                # consume 1 byte
                COMPRESSED_DATA.read_bits(BITS_PER_BYTE)
                size_int += 1            
    except BitBufferReadException:
        # if we attempted to read from the buffer, but there were no more bits in the buffer
        return -1
     
    return COMPRESSED_DATA.byte_index

def test_decompress(in_buffer:bytes, offset:int, final_decompressed_size:int, lookback_size=LZ11_BITS_PER_LOOKBACK, repetition_size=LZ11_BITS_PER_REPETITION) -> bytes:
    return get_compressed_size(in_buffer, offset, final_decompressed_size, lookback_size, repetition_size) != -1

def decompress(in_buffer:bytes, offset:int, final_decompressed_size:int, lookback_size=LZ11_BITS_PER_LOOKBACK, repetition_size=LZ11_BITS_PER_REPETITION) -> bytes:

    COMPRESSED_DATA = bitbuffer(in_buffer, offset)
    output = bytearray()

    min_reptition = get_min_repetitions(lookback_size, repetition_size)

    while len(output) < final_decompressed_size:

        if COMPRESSED_DATA.read_bits(LZ11_BITS_PER_FLAG) == LZ11_FLAG_REPETITION:

            lookback = COMPRESSED_DATA.read_bits(lookback_size)
            # make sure the lookback is to a valid spot
            if lookback >= len(output):
                raise IllegalDecompressionSequenceException()
            
            # because we're reading from the end of the array, better to turn into a negative index
            # cache this, faster than always calculating it
            neg_lookback = -1 - lookback

            count = COMPRESSED_DATA.read_bits(repetition_size) + min_reptition
            # no need to check count, because it will always be valid            

            # if the lookback+count doesn't read from the lookahead, we can just copy it
            if lookback >= count:
                # because of how slicing works, we need positive indices (edge case where lookback == count)
                pos_lookback = len(output) + neg_lookback
                output.extend(output[pos_lookback : pos_lookback + count])

            # we're reading from the lookahead
            else: 

                # # this maybe isn't not worth the check, because there are so few items
                # if lookback > 2: # if we're copying many things
                #     # group them together, and copy multiple values at once
                #     output.extend(output[neg_lookback :])
                #     count -= lookback

                # copy the rest over manually
                while count > 0:
                    # this is where the lookback as negative works best
                    output.append(output[neg_lookback])
                    count -= 1

        else: # FLAG_ORIGINAL
            # write one byte
            output.append(COMPRESSED_DATA.read_bits(BITS_PER_BYTE))
    
    return bytes(output)


def compress(in_buffer: bytes, lookback_size=LZ11_BITS_PER_LOOKBACK, repetition_size=LZ11_BITS_PER_REPETITION) -> bytes:
    # bytes are immutable, no need to copy
    RAW_DATA = in_buffer
    output_bitbuffer = bitbuffer()

    min_reptition = get_min_repetitions(lookback_size, repetition_size)

    # 2**11 - 1 = 2047 bytes to lookback for this pattern
    MAX_LOOKBACK = 2**lookback_size - 1
    # 0 will represent something of size MIN_REPETITION_SIZE, so we can represent larger strings
    MAX_REPETITION_COUNT = min_reptition + 2**repetition_size - 1

    # caching this value, as it won't change
    RAW_DATA_LENGTH = len(RAW_DATA)

    # this will be the index into the raw data to reference the current sequence we're trying to compress
    raw_pointer = 0

    while raw_pointer < RAW_DATA_LENGTH:
        # search_indices
        min_search_index = max(raw_pointer - MAX_LOOKBACK, 0)                       # at least 0, no negative indices
        max_search_index = min(RAW_DATA_LENGTH, raw_pointer + MAX_REPETITION_COUNT) # don't overshoot the end of the array
               
        best_len = -1
        best_index = -1

        # start looking for just 1 byte
        search_size = 1

        while ((search_size <= MAX_REPETITION_COUNT) and        # we can represent the length of the find
               (raw_pointer + search_size < max_search_index)   # we don't look outside the buffer constraints
            ):
            # try to find a sequence
            # first time round: of length 1
            # other times round: longer than the sequence we found
            new_found_index = RAW_DATA.find(
                RAW_DATA[raw_pointer : raw_pointer + search_size],
                min_search_index,
                max_search_index
            )

            if ((new_found_index == -1) or         # we didn't find the sequence
                (new_found_index >= raw_pointer)): # the sequence starts in the back buffer
                break

            # we found a sequence! save it for later
            best_index = new_found_index
            best_len = search_size

            # next loop around look for a longer sequence
            search_size += 1
            # optimization, actually helps to cache this value
            search_size_m_1 = search_size - 1
            
            # let's just check to see if the index that we found actually contains a larger sequence
            # we know for sure it matches one byte, but let's see if it actually matches more
            while ((search_size <= MAX_REPETITION_COUNT) and               # if we haven't reached max size
                   (raw_pointer + search_size_m_1 < max_search_index) and  # if we're still looking inside the buffer
                   (   
                       RAW_DATA[new_found_index + search_size_m_1] == 
                       RAW_DATA[raw_pointer     + search_size_m_1]
                   )                                                       # if the found index matches a longer sequence
                ):
                # this sequence matches for another byte! save the length, and try again
                best_len = search_size
                search_size_m_1 = search_size
                search_size += 1

            # when this loop finishes, if it hasn't matched the max number of bytes,
            # it will attempt to search for a longer match, but we can narrow the search space,
            # we know there isn't a match before where we found this match, as `.find` would have matched the earliest match of bytes 
            min_search_index = new_found_index

        # end of search, we found the best match that we could to our sequence

        # if a sequence wasn't long enough, we need to write a single byte
        # this also handles if not found, best_len == -1
        if best_len < min_reptition:
            
            output_bitbuffer.write_bits(LZ11_FLAG_ORIGINAL,         LZ11_BITS_PER_FLAG)
            output_bitbuffer.write_bits(RAW_DATA[raw_pointer], BITS_PER_BYTE)

            raw_pointer += 1
        
        else: # repetition data
            output_bitbuffer.write_bits(LZ11_FLAG_REPETITION,              LZ11_BITS_PER_FLAG)
            output_bitbuffer.write_bits(raw_pointer - best_index - 1, lookback_size)   # distance from head of output
            output_bitbuffer.write_bits(best_len - min_reptition,     repetition_size) # length, with subtraction to represent it efficiently

            raw_pointer += best_len

    return output_bitbuffer.to_bytes()

MAX_PRINTED_STATEMENTS = 10
printed_statements = 0

def print_count(*args,**kwargs) -> bool:
    global printed_statements, MAX_PRINTED_STATEMENTS
    print(*args, **kwargs)
    printed_statements = printed_statements + 1
    return printed_statements >= MAX_PRINTED_STATEMENTS

def main():

    path_to_compress = "shakespeare.txt"

    compressed_output_path = path_to_compress + "_compressed"
    decompressed_output_path = path_to_compress + "_decompressed"

    with open(path_to_compress, "rb") as f:
        data = f.read()
    data = data[:0x80000]
    import time
    start = time.time()
    compressed_data = compress(data)
    end   = time.time()
    print(f"compression time: {end-start:.4f}s")

    # with open(compressed_output_path, "wb") as f:
    #     f.write(compressed_data)

    start = time.time()
    decompressed_data = decompress(compressed_data, len(data))
    end   = time.time()
    print(f"decompression time: {end-start:.4f}s")
    
    # with open(decompressed_output_path, "wb") as f:
    #     f.write(decompressed_data)

    matching = (data == decompressed_data)

    print(f"Data matches: {matching}")


    if not matching:
        for i in range(max(len(data), len(decompressed_data))):
            if i >= len(data):
                if print_count(f"data missing index {i}"): return
            if i >= len(decompressed_data):
                if print_count(f"decompressed_data missing index {i}"): return
            if i <  len(data)and i < len(decompressed_data) and decompressed_data[i] != data[i]:
                if print_count(f"{i=}, {decompressed_data[i]=}, {data[i]}"): return
        return
    print(f"Compression ratio : {len(compressed_data) / len(data):.3f}")

    import timeit
    iters = 100
    print(f"sampling {iters} time(s) for a more accurate idea of timing")
    print(f"       compress: {timeit.timeit(lambda: compress(data), number=iters) / iters : 0.4}")
    print(f"     decompress: {timeit.timeit(lambda: decompress(compressed_data, len(data)), number=iters) / iters: 0.4}")
    print(f"test decompress: {timeit.timeit(lambda: test_decompress(compressed_data, len(data)), number=iters) / iters: 0.4}")


if __name__ == "__main__":
    main()
