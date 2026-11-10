"""The Crater Park lenticular cap cloud masters: M_CraterCloud and M_CraterCloudVeil, owned by adopted/craterpark/cloud.

The adopted record retains its pinned cloud generator sources (cloud.py, cloud_build.py, crater_cloud_material.py) as a
generator record; both materials become source-pinned material-master records.
"""
FAMILY = {
    'name': 'craterpark_cloud',
    'adopted': 'adopted/craterpark/cloud',
    'owner': 'shared/craterpark/cloud',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'crater_cloud_masters.py',
    'helpers': ['master_haze.py'],
    'donor': 'games/yorimichi/unreal/Scripts/crater_cloud_material.py',
    'donor_lines': {'crater_cloud': '45-131'},
    'generator': True,
    'fallback': 'master/craterpark/cloud',
    'masters': [
        {'id': 'master/craterpark/cloud', 'package': '/Game/CraterPark/Cloud/M_CraterCloud',
         'builder': 'crater_cloud', 'reads': [], 'inputs': [], 'arguments': {'veil': False}},
        {'id': 'master/craterpark/cloud-veil', 'package': '/Game/CraterPark/Cloud/M_CraterCloudVeil',
         'builder': 'crater_cloud', 'reads': [], 'inputs': [], 'arguments': {'veil': True}},
    ],
}
