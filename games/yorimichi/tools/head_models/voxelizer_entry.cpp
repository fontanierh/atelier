#include <torch/extension.h>
#include "api.h"

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("mesh_to_flexible_dual_grid_cpu", &mesh_to_flexible_dual_grid_cpu,
          py::call_guard<py::gil_scoped_release>());
}
