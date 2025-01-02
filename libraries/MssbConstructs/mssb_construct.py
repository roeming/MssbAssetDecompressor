import construct as cs

GECKO_FLOAT   = cs.Float32b
GECKO_DOUBLE  = cs.Float64b
GECKO_U32     = cs.Int32ub
GECKO_S32     = cs.Int32sb
GECKO_U16     = cs.Int16ub
GECKO_S16     = cs.Int16sb
GECKO_U8      = cs.Int8ub
GECKO_S8      = cs.Int8sb
GECKO_POINTER = GECKO_U32

class UnvalidatedCString(cs.Adapter):
    def _decode(self, obj, ctx, path):
        return "".join(chr(x) for x in obj)

    def _encode(self, obj, ctx, path):
        return bytes([ord(x) for x in obj] + [0])

def _whenToStopReadingCString(obj, ctx):
    if obj == 0: raise cs.CancelParsing

GECKO_STRING = UnvalidatedCString(cs.GreedyRange(GECKO_U8 * _whenToStopReadingCString))
# previous definition, but fails on sjis strings
# GECKO_STRING = cs.CString("ascii")

def retrieve_base_pointer():
    return "pBase" / cs.Computed(cs.this._.pBase)

def make_me_base_pointer():
    return "pBase" / cs.Tell

class ValidatePointerIsntNull(cs.Validator):
    def _validate(self, obj, ctx, path):
        return obj != 0

def PointerToStruct(struct: cs.Construct, fieldName: type[None | str] = None, nullable=False):
    return cs.Struct(
        # get the base offset from our parent
        retrieve_base_pointer(),
        # read a pointer (consume a pointer, otherwise read from a field in the parent)
        "p" / (GECKO_POINTER if fieldName == None else cs.Computed(lambda ctx : ctx._[fieldName])),
        # make bool for valid pointer
        "validPointer" / (cs.Computed(cs.this.p != 0) if nullable else ValidatePointerIsntNull(cs.Computed(cs.this.p != 0))),
        # if the pointer is valid, read the struct, add the base
        "valueAtPointer" / cs.If(cs.this.validPointer, cs.Pointer(cs.this.pBase + cs.this.p, struct))
    )


def PointerToArray(struct: cs.Construct, count: type[int | str], fieldName: type[None | str] = None, nullable=False):
    if isinstance(count, str):
        count = cs.this._[count]
        
    return PointerToStruct(struct[count], fieldName, nullable)


def ArrayOfPointers(struct: cs.Construct, count: type[int | str], fieldName: type[None | str] = None, nullable=False):

    if isinstance(count, str):
        count = cs.this._[count]

    return cs.Struct(
        retrieve_base_pointer(),
        (fieldName / cs.Computed(cs.this._[fieldName])) if fieldName else cs.Pass,
        "pointerArray" / PointerToStruct(struct, None if fieldName == None else "_."+fieldName, nullable)[count]
    )

VEC3F  = cs.Struct(
    "x" / GECKO_FLOAT,
    "y" / GECKO_FLOAT,
    "z" / GECKO_FLOAT
)

def get_struct_from_offset(offset_index:int, struct:cs.Construct):
    return cs.Struct(
        make_me_base_pointer(),
        # other parts of the file, skipping for now
        cs.Padding(4 * offset_index),
        # pointer into file
        "pData" / PointerToStruct(struct, nullable=False)
    )

def attempt_to_understand_file_section(b:bytes, offset_index:int, struct:cs.Construct):
    file_with_struct = get_struct_from_offset(offset_index, struct)

    try:
        outData = file_with_struct.parse(b)
    except cs.ConstructError as e:
        print(e)
        return None
       
    return outData.pData.valueAtPointer

class RangeValidator(cs.Validator):
    def __init__(self, subcon: cs.Construct, min, max, includes_max = False) -> None:
        super().__init__(subcon)
        self.min = min
        self.max = max
        self.includes_max = includes_max
    def _validate(self, obj, ctx, path):
        if self.includes_max:
            return self.min <= obj <= self.max
        else:
            return self.min <= obj < self.max
    
class CollectionValidator(cs.Validator):
    def __init__(self, subcon: cs.Construct, collection) -> None:
        super().__init__(subcon)
        self.collection = collection
    
    def _validate(self, obj, ctx, path):
        return obj in self.collection