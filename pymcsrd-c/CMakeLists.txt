cmake_minimum_required(VERSION 3.25)
project(mcsr_shortest_path_thingy C)

set(CMAKE_C_STANDARD 11)

set(Python_FIND_STRATEGY LOCATION)
if(NOT DEFINED Python3_ROOT_DIR)
    set(Python3_ROOT_DIR /usr)
endif()
set(Python3_FIND_VIRTUALENV ONLY)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)

add_executable(shortest_path src/main.c src/lib.c)
target_compile_options(shortest_path PRIVATE -Wall -Wextra -pedantic)

add_library(pymcsrd_c SHARED src/lib.c src/pylib.c)
target_include_directories(pymcsrd_c PUBLIC src ${Python3_INCLUDE_DIRS})
target_link_libraries(pymcsrd_c PUBLIC ${Python3_LIBRARIES})
target_compile_definitions(pymcsrd_c PUBLIC PY_SSIZE_T_CLEAN)
target_compile_options(pymcsrd_c PRIVATE -Wall -Wextra -pedantic)
set_target_properties(pymcsrd_c PROPERTIES PREFIX "")
set_target_properties(pymcsrd_c PROPERTIES OUTPUT_NAME "pymcsrd_c.${Python3_SOABI}")
