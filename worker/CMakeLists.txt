cmake_minimum_required(VERSION 3.13)
project(ava-manager)

if(AVA_MANAGER_GALVANIC)
  add_subdirectory(galvanic)
endif()

if(AVA_MANAGER_KATANA)
  add_subdirectory(katana)
endif()
