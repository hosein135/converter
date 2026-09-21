"""Fix AVM CMake install dirs for Nix (absolute GNUInstallDirs paths)."""

from pathlib import Path


def main() -> None:
    install = Path("cmake/avm_install.cmake")
    text = install.read_text()
    repls = [
        (
            'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_INCLUDEDIR}/avm")',
            'DESTINATION "${CMAKE_INSTALL_FULL_INCLUDEDIR}/avm")',
        ),
        (
            'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}/pkgconfig")',
            'DESTINATION "${CMAKE_INSTALL_FULL_LIBDIR}/pkgconfig")',
        ),
        (
            'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}")',
            'DESTINATION "${CMAKE_INSTALL_FULL_LIBDIR}")',
        ),
        (
            'DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_BINDIR}")',
            'DESTINATION "${CMAKE_INSTALL_FULL_BINDIR}")',
        ),
        (
            "-DCMAKE_INSTALL_INCLUDEDIR=${CMAKE_INSTALL_INCLUDEDIR}",
            "-DCMAKE_INSTALL_FULL_INCLUDEDIR=${CMAKE_INSTALL_FULL_INCLUDEDIR}",
        ),
        (
            "-DCMAKE_INSTALL_LIBDIR=${CMAKE_INSTALL_LIBDIR}",
            "-DCMAKE_INSTALL_FULL_LIBDIR=${CMAKE_INSTALL_FULL_LIBDIR}",
        ),
    ]
    for old, new in repls:
        if old not in text:
            raise SystemExit(f"avm_install.cmake: missing {old!r}")
        text = text.replace(old, new)
    install.write_text(text)

    pc = Path("cmake/pkg_config.cmake")
    pct = pc.read_text()
    pct = pct.replace(
        '"CMAKE_INSTALL_INCLUDEDIR"',
        '"CMAKE_INSTALL_FULL_INCLUDEDIR"',
    )
    pct = pct.replace(
        '"CMAKE_INSTALL_LIBDIR"',
        '"CMAKE_INSTALL_FULL_LIBDIR"',
    )
    old_block = """set(prefix "${CMAKE_INSTALL_PREFIX}")
set(bindir "${CMAKE_INSTALL_BINDIR}")
set(includedir "${CMAKE_INSTALL_INCLUDEDIR}")
set(libdir "${CMAKE_INSTALL_LIBDIR}")"""
    new_block = """get_filename_component(prefix "${CMAKE_INSTALL_FULL_INCLUDEDIR}" DIRECTORY)
get_filename_component(exec_prefix "${CMAKE_INSTALL_FULL_LIBDIR}" DIRECTORY)
get_filename_component(includedir "${CMAKE_INSTALL_FULL_INCLUDEDIR}" NAME)
get_filename_component(libdir "${CMAKE_INSTALL_FULL_LIBDIR}" NAME)"""
    if old_block not in pct:
        raise SystemExit("pkg_config.cmake: install-dir block not found")
    pct = pct.replace(old_block, new_block)
    pct = pct.replace(
        'file(APPEND "${pkgconfig_file}" "exec_prefix=\\${prefix}\\n")',
        'file(APPEND "${pkgconfig_file}" "exec_prefix=${exec_prefix}\\n")',
    )
    pc.write_text(pct)


if __name__ == "__main__":
    main()
