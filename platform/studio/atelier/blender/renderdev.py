import bpy

def enable_metal():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    # Scene-specialized Metal kernels recompile for minutes whenever the shader graph
    # changes; the generic kernels are a few percent slower but start instantly.
    if hasattr(prefs, "kernel_optimization_level"):
        prefs.kernel_optimization_level = "OFF"
    bpy.context.scene.cycles.device = "GPU"
    return any(d.type == "METAL" and d.use for d in prefs.devices)
