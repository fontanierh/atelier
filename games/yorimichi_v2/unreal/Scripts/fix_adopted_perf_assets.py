"""Fix 13 editor-owned non-POT/uncompressed/4K textures and strip unused collision/CPU buffers on 50 MegaPark render meshes."""
import unreal as U

EAL = U.EditorAssetLibrary
U.load_module('StaticMeshEditor')
SME = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)

MEGAPARK_NON_POT = [
    '/Game/MegaPark/Textures/T_2c70170a000b004a',
    '/Game/MegaPark/Textures/T_00004eb103e3870a',
    '/Game/MegaPark/Textures/T_0000127a03e3870a',
]

IMPOSTOR_NORMALS = [
    '/Game/Japan/Textures/T_ForestNormalDefault',
    '/Game/Japan/Textures/T_Tree_Forest_Ginkgo_normal',
    '/Game/Japan/Textures/T_Tree_Forest_Maple_normal',
    '/Game/Japan/Textures/T_Tree_Forest_Oak_normal',
    '/Game/Japan/Textures/T_Tree_Forest_Pine_normal',
    '/Game/Japan/Textures/T_Tree_Tuscan_Cypress_normal',
    '/Game/Japan/Textures/T_Tree_Tuscan_Oak_normal',
    '/Game/Japan/Textures/T_Tree_Tuscan_Olive_normal',
    '/Game/Japan/Textures/T_Tree_Tuscan_Pine_normal',
]

GALLEON_4K = '/Game/Brinecove/Textures/T_BC_hero_galleon-hull_0'

MEGAPARK_RENDER_MESHES = ['/Game/MegaPark/Meshes/SM_MP_04CCB1FDB63D6C87', '/Game/MegaPark/Meshes/SM_MP_072BEA8B3D376763', '/Game/MegaPark/Meshes/SM_MP_0D601DA7CE12176C', '/Game/MegaPark/Meshes/SM_MP_1700B3D8FB9AB703', '/Game/MegaPark/Meshes/SM_MP_1E077DDD5C16EF04', '/Game/MegaPark/Meshes/SM_MP_20EF3EEEEFC658B7', '/Game/MegaPark/Meshes/SM_MP_2386D0A7C698F48A', '/Game/MegaPark/Meshes/SM_MP_23BEE1BECD19BE5A', '/Game/MegaPark/Meshes/SM_MP_2A4ACEDB492E1152', '/Game/MegaPark/Meshes/SM_MP_44214047ACFF84CE', '/Game/MegaPark/Meshes/SM_MP_497D79468122553D', '/Game/MegaPark/Meshes/SM_MP_49FCE212AF609520', '/Game/MegaPark/Meshes/SM_MP_4F30D544AAE05618', '/Game/MegaPark/Meshes/SM_MP_517C499144026147', '/Game/MegaPark/Meshes/SM_MP_5B3CA6D5163630B2', '/Game/MegaPark/Meshes/SM_MP_6988628140DF5E40', '/Game/MegaPark/Meshes/SM_MP_6A5170620386E3BA', '/Game/MegaPark/Meshes/SM_MP_78C490ADD37F1397', '/Game/MegaPark/Meshes/SM_MP_78DABDFB1C74ABB9', '/Game/MegaPark/Meshes/SM_MP_7D05C890200776E1', '/Game/MegaPark/Meshes/SM_MP_7F33C0EB48F375F5', '/Game/MegaPark/Meshes/SM_MP_80C8F2395B012D9F', '/Game/MegaPark/Meshes/SM_MP_97881E4457D561E6', '/Game/MegaPark/Meshes/SM_MP_97E970447A822ABF', '/Game/MegaPark/Meshes/SM_MP_9D8FA15A3EB6BF2F', '/Game/MegaPark/Meshes/SM_MP_A41E3A10C48B5DA3', '/Game/MegaPark/Meshes/SM_MP_A79ABAE2264637B0', '/Game/MegaPark/Meshes/SM_MP_B482B33EDA279C4A', '/Game/MegaPark/Meshes/SM_MP_B5FC108CCBDF28D8', '/Game/MegaPark/Meshes/SM_MP_B99C161736634778', '/Game/MegaPark/Meshes/SM_MP_BB462637C794A55E', '/Game/MegaPark/Meshes/SM_MP_BD340E588EB1B8A8', '/Game/MegaPark/Meshes/SM_MP_BFD920538C420ABC', '/Game/MegaPark/Meshes/SM_MP_C41D333E7557EA22', '/Game/MegaPark/Meshes/SM_MP_C809B0BD30B056FC', '/Game/MegaPark/Meshes/SM_MP_C888FCF815E09C53', '/Game/MegaPark/Meshes/SM_MP_D0A698D4B8E19DA3', '/Game/MegaPark/Meshes/SM_MP_D20218BAEC3CAEF8', '/Game/MegaPark/Meshes/SM_MP_D9800C0C164BE6DF', '/Game/MegaPark/Meshes/SM_MP_DBDE3D0EED110A40', '/Game/MegaPark/Meshes/SM_MP_DCEFF8F63009B573', '/Game/MegaPark/Meshes/SM_MP_DE2ECF040F079D1C', '/Game/MegaPark/Meshes/SM_MP_E12A6008908C21E6', '/Game/MegaPark/Meshes/SM_MP_E33675EB8A7CAFB7', '/Game/MegaPark/Meshes/SM_MP_EB6AB76807F5192A', '/Game/MegaPark/Meshes/SM_MP_F03BD8AEFE8D7AA1', '/Game/MegaPark/Meshes/SM_MP_F1A2EEC1D33D38AF', '/Game/MegaPark/Meshes/SM_MP_F3ACAD491674B546', '/Game/MegaPark/Meshes/SM_MP_FA1B51A9664C0BC5', '/Game/MegaPark/Meshes/SM_MP_FCCBD6F3DD6D6D2E']


def save_tex(tex, path, expected):
    for prop, want in expected.items():
        got = tex.get_editor_property(prop)
        if got != want:
            raise RuntimeError(f'{path}: {prop} read back {got!r}, expected {want!r}')
    if not EAL.save_loaded_asset(tex, False):
        raise RuntimeError(f'could not save {path}')
    U.log(f'V2 FIXED TEXTURE {path}')


for path in MEGAPARK_NON_POT:
    tex = EAL.load_asset(path)
    tex.set_editor_property('power_of_two_mode', U.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO)
    tex.set_editor_property('mip_gen_settings', U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
    tex.set_editor_property('max_texture_size', 2048)
    save_tex(tex, path, {
        'power_of_two_mode': U.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO,
        'mip_gen_settings': U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP,
        'max_texture_size': 2048,
    })

for path in IMPOSTOR_NORMALS:
    tex = EAL.load_asset(path)
    tex.set_editor_property('srgb', False)
    tex.set_editor_property('compression_settings', U.TextureCompressionSettings.TC_BC7)
    tex.set_editor_property('mip_gen_settings', U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
    save_tex(tex, path, {
        'srgb': False,
        'compression_settings': U.TextureCompressionSettings.TC_BC7,
        'mip_gen_settings': U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP,
    })

gtex = EAL.load_asset(GALLEON_4K)
gtex.set_editor_property('max_texture_size', 2048)
gtex.set_editor_property('mip_gen_settings', U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
save_tex(gtex, GALLEON_4K, {
    'max_texture_size': 2048,
    'mip_gen_settings': U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP,
})

for path in MEGAPARK_RENDER_MESHES:
    if '/SM_MP_' not in path or path.endswith('/SM_MP_Seam'):
        raise RuntimeError(f'refusing non-adopted-render MegaPark mesh: {path}')
    mesh = EAL.load_asset(path)
    if SME.get_simple_collision_count(mesh) or SME.get_convex_collision_count(mesh):
        SME.remove_collisions(mesh)
    mesh.set_editor_property('allow_cpu_access', False)
    body = mesh.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag', U.CollisionTraceFlag.CTF_USE_DEFAULT)
    body.set_editor_property('never_needs_cooked_collision_data', True)
    if not EAL.save_loaded_asset(mesh, False):
        raise RuntimeError(f'could not save {path}')
    U.log(f'V2 STRIPPED RENDER-ONLY COLLISION {path}')
