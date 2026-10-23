# City constructor parameters

Each logical city asset owns its initial palette and random-stream position. These are
source authoring parameters, measured from the original ordered city construction and
checked against complete ordered geometry, normals, UV/color channels, material slots,
placement frames and authored collision boxes. They preserve the initial appearance
while removing dependence on whichever sibling happened to run first.

Each parameter file and its explicitly selected shared palette enter the consuming
constructor's input identity; the whole library does not. Editing a sibling
must not silently change this asset's colors or random variation. A deliberate color
change belongs in this asset's parameters or its explicit constructor palette. The
provenance records describe the initial comparison; they are not receiving certificates
and do not exempt future source, export or native validation.
