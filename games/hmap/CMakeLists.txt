# Harvest Moon: Animal Parade - engine plug-in.
# Built through the engine's top-level CMakeLists with -DWP_GAME=hmap
# (`python hmap.py build` does this). Adapted from games/wiiparty/CMakeLists.txt.

set(HMAP_GENERATED "${CMAKE_SOURCE_DIR}/build/hmap/generated")

file(GLOB HMAP_DSP_SOURCES CONFIGURE_DEPENDS "${HMAP_GENERATED}/dsp/*.cpp")
if(HMAP_DSP_SOURCES)
    target_sources(wp_engine PRIVATE ${HMAP_DSP_SOURCES})
    set_source_files_properties(${HMAP_DSP_SOURCES} PROPERTIES COMPILE_OPTIONS -O2)
else()
    # No ahead-of-time DSP translation yet: the engine interprets the audio microcode.
    target_sources(wp_engine PRIVATE "${CMAKE_SOURCE_DIR}/engine/src/audio/no_dsp_code.cpp")
endif()

file(GLOB HMAP_DOL_SOURCES CONFIGURE_DEPENDS "${HMAP_GENERATED}/dol/*.cpp")
file(GLOB_RECURSE HMAP_MODULE_SOURCES CONFIGURE_DEPENDS "${HMAP_GENERATED}/modules/*.cpp")
if(NOT HMAP_DOL_SOURCES)
    message(STATUS "No generated code in ${HMAP_GENERATED}/dol: run `python hmap.py recompile` first")
    return()
endif()

add_library(hmap_code STATIC game.cpp ${HMAP_DOL_SOURCES})
set_source_files_properties(${HMAP_DOL_SOURCES} ${HMAP_MODULE_SOURCES} PROPERTIES COMPILE_OPTIONS "${WP_CODE_OPT}")
target_include_directories(hmap_code PUBLIC "${HMAP_GENERATED}/dol")
if(HMAP_MODULE_SOURCES)
    target_sources(hmap_code PRIVATE ${HMAP_MODULE_SOURCES})
else()
    target_sources(hmap_code PRIVATE "${CMAKE_SOURCE_DIR}/engine/src/core/no_modules.cpp")
endif()
target_link_libraries(hmap_code PUBLIC wp_engine)
target_compile_options(hmap_code PRIVATE -Wall -Wextra -Wno-unused-label -Wno-unused-parameter -Wno-clobbered)

add_executable(hmap)
target_link_libraries(hmap PRIVATE wp_app "$<LINK_GROUP:RESCAN,hmap_code,wp_engine>")
target_compile_options(hmap PRIVATE -Wall -Wextra)
if(WIN32 AND NOT WP_CONSOLE)
    set_target_properties(hmap PROPERTIES WIN32_EXECUTABLE ON)
endif()
if(WP_AURORA AND WIN32)
    # aurora's prebuilt Dawn (webgpu_dawn.dll, + dxcompiler/dxil it loads at run time) and SDL3
    # must sit next to the executable.
    include("${WP_AURORA_DIR}/cmake/AuroraCopyRuntimeDLLs.cmake")
    aurora_copy_runtime_dlls(hmap)
elseif(TARGET SDL3::SDL3)
    add_custom_command(TARGET hmap POST_BUILD COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_FILE:SDL3::SDL3> $<TARGET_FILE_DIR:hmap>)
endif()
