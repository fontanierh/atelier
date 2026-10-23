"""Trail faces consume final query data before any rendered export."""
from zeppelin.primitives import M,STONE


def construct(queries):
    mesh=M('ZP_Trail')
    for row in queries.value['paths']:
        for p in row['polygons']:
            mesh.poly(p,STONE if row['skirts'] else (.25,.16,.079))
            if row['skirts']:
                for a,b in [(p[0],p[1]),(p[2],p[3])]:
                    mesh.poly([(a[0],a[1],a[2]-.35),(b[0],b[1],b[2]-.35),b,a],STONE)
    return mesh
