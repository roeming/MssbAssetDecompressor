from .mssb_construct import *


class BitToFloatAdaptor(cs.Adapter):
    def __init__(self, subcon: cs.Construct, bit_size: int) -> None:
        super().__init__(subcon)
        self.maxAmount = (1 << bit_size) - 1

    def _decode(self, obj, ctx, path):
        return float(obj / self.maxAmount)

    def _encode(self, obj, ctx, path):
        return int(obj * self.maxAmount)


def make_color_struct(r_size, g_size, b_size, a_size=0, end_padding=0):
    return cs.BitStruct(
        "R" / BitToFloatAdaptor(cs.BitsInteger(r_size), r_size),
        "G" / BitToFloatAdaptor(cs.BitsInteger(g_size), g_size),
        "B" / BitToFloatAdaptor(cs.BitsInteger(b_size), b_size),
        "A" / (BitToFloatAdaptor(cs.BitsInteger(a_size), a_size) if a_size != 0 else cs.Computed(1.0)),
        (cs.Padding(end_padding))
    )


COLOR_565 = make_color_struct(5, 6, 5)
COLOR_888 = make_color_struct(8, 8, 8)
COLOR_888X = make_color_struct(8, 8, 8, 0, 8)
COLOR_4444 = make_color_struct(4, 4, 4, 4)
COLOR_6666 = make_color_struct(6, 6, 6, 6)
COLOR_8888 = make_color_struct(8, 8, 8, 8)
