find_path(
    UV_INCLUDE_DIR
    NAMES uv.h
    PATHS "${XMRIG_DEPS}" ENV "XMRIG_DEPS"
    PATH_SUFFIXES "include"
    NO_DEFAULT_PATH
)

find_path(UV_INCLUDE_DIR NAMES uv.h)

find_library(
    UV_LIBRARY
    NAMES libuv.a uv libuv
    PATHS "${XMRIG_DEPS}" ENV "XMRIG_DEPS"
    PATH_SUFFIXES "lib"
    NO_DEFAULT_PATH
)

find_library(UV_LIBRARY NAMES libuv.a uv libuv)

if (XMRIG_DEPS)
    set(UV_INCLUDE_DIR "${XMRIG_DEPS}/include" CACHE PATH "libuv include directory" FORCE)
    set(UV_LIBRARY "${XMRIG_DEPS}/lib/libuv.a" CACHE FILEPATH "libuv library" FORCE)
endif()

set(UV_LIBRARIES ${UV_LIBRARY})
set(UV_INCLUDE_DIRS ${UV_INCLUDE_DIR})

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(UV DEFAULT_MSG UV_LIBRARY UV_INCLUDE_DIR)
