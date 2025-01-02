from construct.core import Construct
from .mssb_construct_color import *

QUANTIZE_FLOAT_DICT = {
    0 : GECKO_U16,
    1 : GECKO_FLOAT,
    2 : GECKO_U16,
    3 : GECKO_S16,
    4 : GECKO_U8, 
    5 : GECKO_S8
}

QUANTIZE_COLOR_DICT = {
    0 : COLOR_565,
    1 : COLOR_888,
    2 : COLOR_888X,
    3 : COLOR_4444,
    4 : COLOR_6666,
    5 : COLOR_8888
}

class FloatQuantizeAdaptor(cs.Adapter):
    def _decode(self, obj, ctx, path):
        return obj / ctx.quantizeInfo.shiftAmount

    def _encode(self, obj, ctx, path):
        return int(obj * ctx.quantizeInfo.shiftAmount)

# quantizedValue = cs.Struct(
#     "rawValue" / cs.Switch(cs.this._.quantizeInfo.quantizeValue, QUANTIZE_TYPE_DICT, default=cs.Error),
#     "shiftedValue" / cs.Computed(cs.this.rawValue / cs.this._.quantizeInfo.shiftAmount)
# )

displayObjectFloatComponents = cs.Struct(
    # displayObjectPositionHeader->pPositionArray->valueAtPointer (us)
    # displayObjectPositionHeader->quantizeInfo (target)
    # so up 2 parents, and then into the quantize info
    "quantizeInfo" / cs.Computed(cs.this._._.quantizeInfo),
    "myValues" / FloatQuantizeAdaptor(cs.Switch(cs.this.quantizeInfo.quantizeValue, QUANTIZE_FLOAT_DICT, default=cs.Error))[cs.this._._.numberOfComponents],
)

displayObjectColorComponents = cs.Struct(
    # displayObjectColorHeader->pColorArray->valueAtPointer (us)
    # displayObjectColorHeader->quantizeInfo (target)
    "myValues" / cs.Switch(cs.this._._.quantizeInfo.quantizeValue, QUANTIZE_COLOR_DICT, default=cs.Error),
)

displayObjectPositionHeader_QuantizedData = cs.Bitwise(cs.Struct(
    "quantizeValue" / cs.Nibble,
    "shift" / cs.Nibble,
    "shiftAmount" / cs.Computed(1 << cs.this.shift)
))


displayObjectPositionHeader = cs.Struct(
    retrieve_base_pointer(),
    "offsetToPositionArray" / GECKO_POINTER,
    "numberOfPositions" / GECKO_U16,
    "quantizeInfo" / displayObjectPositionHeader_QuantizedData,
    "numberOfComponents" / GECKO_U8, # 2 or 3
    "pPositionArray" / PointerToArray(displayObjectFloatComponents, "numberOfPositions", "offsetToPositionArray"),
)

displayObjectColorHeader_QuantizedData = cs.Bitwise(cs.Struct(
    "quantizeValue" / cs.Nibble,
    cs.Nibble,
))

displayObjectColorHeader = cs.Struct(
    retrieve_base_pointer(),
    "offsetToColorArray" / GECKO_POINTER,
    "numberOfColors" / GECKO_U16,
    "quantizeInfo" / displayObjectColorHeader_QuantizedData,
    "numberOfComponents" / GECKO_U8,  # 3 or 4
    "pColorArray" / PointerToArray(displayObjectColorComponents, "numberOfColors", "offsetToColorArray"),
)

displayObjectTextureHeader = cs.Struct(
    retrieve_base_pointer(),
    "offsetToTextureArray" / GECKO_POINTER,
    "numberOfTexCoords" / GECKO_U16,
    "quantizeInfo" / displayObjectPositionHeader_QuantizedData,
    "numberOfComponents" / GECKO_U8,  # 1 or 2
    "pName" / PointerToStruct(GECKO_STRING),
    cs.Padding(4),
    "pTextureCoordArray" / PointerToArray(displayObjectFloatComponents, "numberOfTexCoords", "offsetToTextureArray"),
)

displayObjectLightingHeader = cs.Struct(
    retrieve_base_pointer(),
    "offsetToNormalArray" / GECKO_POINTER,
    "numberOfNormals" / GECKO_U16,
    "quantizeInfo" / displayObjectPositionHeader_QuantizedData,
    "numberOfComponents" / GECKO_U8, # 2 or 3
    "ambientLighting" / GECKO_FLOAT,
    "pNormalArray" / PointerToArray(displayObjectFloatComponents, "numberOfNormals", "offsetToNormalArray"),
)

displayObjectPrimitiveList = cs.Struct(
    "byteList" / cs.Array(lambda ctx: ctx._._.primitiveByteSize, GECKO_U8)
    # "byteList" / cs.Array(1, GECKO_U8)
)

displayObjectStateTexture = cs.BitStruct(
    "magFilter" / cs.BitsInteger(4),
    "minFilter" / cs.BitsInteger(4),
    "wrapT" / cs.BitsInteger(4),
    "wrapS" / cs.BitsInteger(4),
    "layer" / cs.BitsInteger(3),
    cs.Const(0, cs.BitsInteger(5)), # unk/unused
    "textureIndex" / cs.BitsInteger(8)
)

displayObjectStateVCD = cs.BitStruct(
    cs.Const(0, cs.BitsInteger(6)), # unused
    "texCoord7" / cs.BitsInteger(2),
    "texCoord6" / cs.BitsInteger(2),
    "texCoord5" / cs.BitsInteger(2),
    "texCoord4" / cs.BitsInteger(2),
    "texCoord3" / cs.BitsInteger(2),
    "texCoord2" / cs.BitsInteger(2),
    "texCoord1" / cs.BitsInteger(2),
    "texCoord0" / cs.BitsInteger(2),
    "color1" / cs.BitsInteger(2),
    "color0" / cs.BitsInteger(2),
    "normal" / cs.BitsInteger(2),
    "position" / cs.BitsInteger(2),
    "posMatrixIndex" / cs.BitsInteger(2),
)

displayObjectMtxLoad = cs.BitStruct(
    "mtxSrcIdx" / cs.BitsInteger(16),
    "mtxDstIdx" / cs.BitsInteger(16),
)

DISPLAY_STATE_DICT = {
    1 : displayObjectStateTexture,
    2 : displayObjectStateVCD,
    3 : displayObjectMtxLoad,
}

displayObjectDisplayState = cs.Struct(
    retrieve_base_pointer(),
    "stateID" / GECKO_U8,
    cs.Padding(3),
    "setting" / cs.Switch(cs.this.stateID, DISPLAY_STATE_DICT, default=cs.Error),
    "offsetToPrimitives" / GECKO_POINTER,
    "primitiveByteSize" / GECKO_U32,
    # "pPrimitives" / PointerToStruct(displayObjectPrimitiveList, "offsetToPrimitives")
)

displayObjectDisplayHeader = cs.Struct(
    retrieve_base_pointer(),
    "offsetToPrimitiveBank" / GECKO_POINTER,
    "offsetToDisplayStateList" / GECKO_POINTER,
    "displayStateCount" / GECKO_U16,
    "pDisplayStates" / PointerToArray(displayObjectDisplayState, "displayStateCount", "offsetToDisplayStateList"),
    cs.Padding(2)
)


displayObjectLayout = cs.Struct(
    make_me_base_pointer(),
    "pPositionData" / PointerToStruct(displayObjectPositionHeader) * "Vertices",
    "pColorData" / PointerToStruct(displayObjectColorHeader) * "Vertex Colors",
    "pTextureData" / PointerToStruct(displayObjectTextureHeader) * "UVs",
    "pLightingData" / PointerToStruct(displayObjectLightingHeader, nullable=True) * "Normals",
    "pDisplayData" / PointerToStruct(displayObjectDisplayHeader) * "Combine all data into triangles",
    "numberOfTextures" / GECKO_U8,
    cs.Const(0xff, GECKO_U8), #unknown
    cs.Padding(2 + 4),
    # bounding box
    "minX" / GECKO_FLOAT,
    "maxX" / GECKO_FLOAT,
    "minY" / GECKO_FLOAT,
    "maxY" / GECKO_FLOAT,
    "minZ" / GECKO_FLOAT,
    "maxZ" / GECKO_FLOAT,
)

geoDescriptor = cs.Struct(
    retrieve_base_pointer(),
    "pDisplayObject" / PointerToStruct(displayObjectLayout),
    "pName" / PointerToStruct(GECKO_STRING),
)

geoHeader = cs.Struct(
    make_me_base_pointer(),
    "vesionNumber" / cs.Const(6012001, GECKO_U32),
    "userDataSize" / GECKO_U32,
    "pUserData" / PointerToArray(GECKO_U8, "userDataSize", nullable=True),
    "numGeomDescriptors" / GECKO_U32,
    "pGeomDescriptors" / PointerToArray(geoDescriptor, "numGeomDescriptors"),
)
