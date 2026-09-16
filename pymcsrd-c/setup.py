from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class build_ext_with_stub(build_ext):
    def run(self):
        super().run()

        build_lib = Path(self.get_finalized_command("build_py").build_lib)

        stub = Path("src/pymcsrd_c.pyi")
        target = build_lib / "pymcsrd_c.pyi"

        target.write_bytes(stub.read_bytes())


setup(
    ext_modules=[
        Extension(
            "pymcsrd_c",
            sources=["src/lib.c", "src/pylib.c"],
            include_dirs=["src"],
            define_macros=[("PY_SSIZE_T_CLEAN", None)],
            extra_compile_args=["-O3", "-march=native"],
        ),
    ],
    cmdclass={"build_ext": build_ext_with_stub},
)
