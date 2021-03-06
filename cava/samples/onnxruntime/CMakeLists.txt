cmake_minimum_required(VERSION 3.13)

get_cmake_property(vars CACHE_VARIABLES)
foreach(var ${vars})
  if (var MATCHES ".*_DIR$" OR var MATCHES ".*_ROOT$")
    #message(STATUS "${var} = [${${var}}]")
    list(APPEND CL_ARGS "-D${var}=${${var}}")
  endif()
endforeach()

project(ava-spec-onnxruntime)

include(ExternalProject)

###### Compile onnxruntime/onnx_dump.c ######

find_package(PkgConfig REQUIRED)
pkg_search_module(GLIB2 REQUIRED glib-2.0)

ExternalProject_Add_Step(cava onnx_dump-nwcc
  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/samples/onnxruntime/onnx_dump.c
  COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/nwcc ${CMAKE_CURRENT_SOURCE_DIR}/samples/onnxruntime/onnx_dump.c -I /usr/local/cuda-10.1/include -I ${CMAKE_CURRENT_SOURCE_DIR}/headers ${GLIB2_CFLAGS}
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  DEPENDEES download
)

set(onnx_dump_install ${AVA_INSTALL_DIR}/onnx_dump_nw)
ExternalProject_Add_Step(cava onnx_dump-link
  COMMAND mkdir -p generated &&
          mkdir -p ${onnx_dump_install}/lib &&
          ln -f -s ${CMAKE_CURRENT_SOURCE_DIR}/headers ${CMAKE_CURRENT_BINARY_DIR}/headers            &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcuda.so.1      &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcublas.so.10   &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcublasLt.so.10 &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcudart.so.10   &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcudnn.so.7     &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcufft.so.10    &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcurand.so.10   &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcusolver.so.10 &&
          ln -f -s ${onnx_dump_install}/lib/libguestlib.so ${onnx_dump_install}/lib/libcusparse.so.10
  WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/..
  DEPENDEES onnx_dump-nwcc
)

ExternalProject_Add(onnx_dump_nw
  PREFIX onnx_dump_nw
  SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/onnx_dump_nw
  BINARY_DIR ${CMAKE_CURRENT_BINARY_DIR}/onnx_dump_nw
  INSTALL_DIR ${onnx_dump_nw}
  DOWNLOAD_COMMAND ""
  CMAKE_ARGS ${CL_ARGS}
             -DCMAKE_C_COMPILER:STRING=${CMAKE_C_COMPILER}
             -DCMAKE_CXX_COMPILER:STRING=${CMAKE_CXX_COMPILER}
             -DCMAKE_INSTALL_PREFIX:PATH=${onnx_dump_install}
  BUILD_ALWAYS ON
  DEPENDS cava
)

###### Compile onnxruntime/onnx_opt.c ######

ExternalProject_Add_Step(cava onnx_opt-nwcc
  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/samples/onnxruntime/onnx_opt.c
  COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/nwcc ${CMAKE_CURRENT_SOURCE_DIR}/samples/onnxruntime/onnx_opt.c -I /usr/local/cuda-10.1/include -I ${CMAKE_CURRENT_SOURCE_DIR}/headers ${GLIB2_CFLAGS}
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  DEPENDEES download
)

set(onnx_opt_install ${AVA_INSTALL_DIR}/onnx_opt_nw)
ExternalProject_Add_Step(cava onnx_opt-link
  COMMAND mkdir -p generated &&
          mkdir -p ${onnx_opt_install}/lib &&
          ln -f -s ${CMAKE_CURRENT_SOURCE_DIR}/headers ${CMAKE_CURRENT_BINARY_DIR}/headers          &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcuda.so.1      &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcublas.so.10   &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcublasLt.so.10 &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcudart.so.10   &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcudnn.so.7     &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcufft.so.10    &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcurand.so.10   &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcusolver.so.10 &&
          ln -f -s ${onnx_opt_install}/lib/libguestlib.so ${onnx_opt_install}/lib/libcusparse.so.10
  WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/..
  DEPENDEES onnx_opt-nwcc
)

ExternalProject_Add(onnx_opt_nw
  PREFIX onnx_opt_nw
  SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/onnx_opt_nw
  BINARY_DIR ${CMAKE_CURRENT_BINARY_DIR}/onnx_opt_nw
  INSTALL_DIR ${onnx_opt_install}
  DOWNLOAD_COMMAND ""
  CMAKE_ARGS ${CL_ARGS}
             -DCMAKE_C_COMPILER:STRING=${CMAKE_C_COMPILER}
             -DCMAKE_CXX_COMPILER:STRING=${CMAKE_CXX_COMPILER}
             -DCMAKE_INSTALL_PREFIX:PATH=${onnx_opt_install}
  BUILD_ALWAYS ON
  DEPENDS cava
)
