"""Reference-led public-space positions shared by layout and mesh builders."""
# x/y, width/depth, autumn crown. Main gameplay route y=150 remains open.
PLAZA_GARDENS = [
    (704.,139.,10.,6.,False), (747.,136.,9.,6.,False),
    (766.,137.,10.,6.,True), (689.,174.,10.,6.,False),
    (713.,158.,9.,6.,False), (740.,156.,6.,4.,True),
    (776.,192.,8.,6.,True), (698.,194.,9.,6.,False),
]
PLAZA_STALLS = [(752.,158.,0),(760.,158.,1),(768.,158.,2)]
PLAZA_CAFE = [(691.,132.),(691.,140.),(700.,126.)]

STREET_GARDENS=[(x,140+s*6.65,s) for x in [441,494,546,601,642] for s in [-1,1]]+[(x,230+s*6.65,s) for x in [873,952,1007,1061,1100] for s in [-1,1]]

HARBOR_STALLS=[(638.,-122.,0),(646.,-122.,1)]
TEMPLES=[(690.,300.,0.),(790.,305.,25.)]
STATION_GARDENS=[(1169.,263.,7.,4.,False),(1201.,263.,7.,4.,True)]
