from mssb_construct import *

boundingBox = cs.Struct(
    "min" / VEC3F,
    "max" / VEC3F
)

enumCollisionFlags = cs.Enum(GECKO_U16, 
    STADIUM_TRIANGLE_TYPE_GRASS             = (0x01),
    STADIUM_TRIANGLE_TYPE_WALL              = (0x02),
    STADIUM_TRIANGLE_TYPE_OOB               = (0x03),
    STADIUM_TRIANGLE_TYPE_FOUL_LINE_MARKERS = (0x04),
    STADIUM_TRIANGLE_TYPE_BACK              = (0x05),
    STADIUM_TRIANGLE_TYPE_DIRT              = (0x06),
    STADIUM_TRIANGLE_TYPE_PIT_WALL          = (0x07),
    STADIUM_TRIANGLE_TYPE_PIT               = (0x08),
    STADIUM_TRIANGLE_TYPE_ROUGH_TERRAIN     = (0x09),
    STADIUM_TRIANGLE_TYPE_WATER             = (0x0A),
    STADIUM_TRIANGLE_TYPE_CHOMP_HAZARD      = (0x0B),
    STADIUM_TRIANGLE_TYPE_FOUL              = (0x80)
)

collisionTriangle = cs.Struct(
    "vertex" / VEC3F,
    "collisionFlags" / enumCollisionFlags,
    "pad" / GECKO_U16
)

collisionVertexCollection = cs.Struct(
    #pad
    "pad" / GECKO_U8,
    # flag is bool
    "isTriangleStrip" / cs.Flag,
    "rawVertCount" / GECKO_U16,
    # only works with ctx, not this.
    "vertCount" / cs.Computed(lambda ctx: (ctx.rawVertCount + 2) if (ctx.isTriangleStrip) else (ctx.rawVertCount * 3)),
    # immediately followed by an array of collision triangles
    "vertexArray" / collisionTriangle[cs.this.vertCount]
)

def whenToStopCollectingTriangles(obj, ctx):
    if obj.rawVertCount == 0: raise cs.CancelParsing

triangleCollectionArray = cs.Struct(
    # use greedy range here, cs.RepeatUntil works in theory, but not compatible with the UI
    "triCollection" / (cs.GreedyRange(collisionVertexCollection * whenToStopCollectingTriangles)),
    # last triCollection has to have a collisionVertexCollection with 0 triangles
    # this solution is technically a triCollection with length 0, but its kinda nicer this way, means you don't have to
    # make a new triangle collection with 0 triangles, just your valid collection
    "pad" / cs.Const(b"\0\0\0\0")
)

collisionHeader = cs.Struct(
    # makes all child pointer elements add this offset, doesn't consume bytes
    make_me_base_pointer(),
    # boxCount, u16
    "boxCount" / GECKO_U16,
    # unknown field
    "pad" / GECKO_U16,
    # pointer to boxes
    "pBoundingBoxes" / PointerToArray(boundingBox, "boxCount"),
    # collection of triangles, it's an array of pointers to these arrays
    "trianglePointerArray" / ArrayOfPointers(triangleCollectionArray, "boxCount")
)

def write_collision(outData: cs.Struct, outFileName: str):

    def formatVertex(vertex):
        return f"v {vertex.x} {vertex.y} {vertex.z}\n"
    class ObjWriter:
        def __init__(self) -> None:
            self.cached_verts = {}

        def writeVert(self, fileRef, vertex):
            formatted_vertex = formatVertex(vertex)
            index = self.cached_verts.get(formatted_vertex, None)
            if index == None:
                fileRef.write(formatted_vertex)
                index = len(self.cached_verts) + 1
                self.cached_verts[formatted_vertex] = index
            return index

        def writeFace(self, fileRef, vertexA, vertexB, vertexC):
            a = self.writeVert(fileRef, vertexA)
            b = self.writeVert(fileRef, vertexB)
            c = self.writeVert(fileRef, vertexC)
            fileRef.write(f"f {a} {b} {c}\n")
    
    objWriter = ObjWriter()

    with open(outFileName, "w") as f:
        for someTriangles in outData.pCollision.valueAtPointer.trianglePointerArray.pointerArray:
            for collection in someTriangles.valueAtPointer.triCollection:
                isTriangleStrip = collection.isTriangleStrip

                i = 0
                vertCount = collection.vertCount
                while (i < (vertCount - 2)):
                    objWriter.writeFace(f, collection.vertexArray[i].vertex, collection.vertexArray[i+1].vertex, collection.vertexArray[i+2].vertex)
                    if isTriangleStrip:
                        i += 1
                    else:
                        i += 3
