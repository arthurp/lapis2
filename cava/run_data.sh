#! /bin/bash

CAVA_DIR="$PWD"

. /home/amp/LocalInstalls/conda/miniconda3/bin/activate lapis

I_ARGS="-I /usr/lib/gcc/x86_64-linux-gnu/9/include -I $CONDA_PREFIX/include/ -I $CAVA_DIR/headers -I $CAVA_DIR/input"

trash output
mkdir -p output

function run_api {
  API=$1
  PREFIX=$2
  RULEFILE=${3:-$API.lapis}
  OTHER_ARGS="--dump --funclist input/$API.funcs"
  echo "$API ($RULEFILE)"
  # Lapis 2
  echo -n Lapis 2
  python -m nightwatch.main $I_ARGS input/$API.nw.c --rulefile input/$RULEFILE $OTHER_ARGS --no-ava-rules > output/$API.lapis.out 2> /dev/null
  mv ${PREFIX}_nw output/${PREFIX}_nw_lapis
  # AvA without rules
  echo -n "  AvA (without rules)"
  python -m nightwatch.main $I_ARGS input/$API.ava.nw.c $OTHER_ARGS --no-ava-rules > output/$API.ava.norules.out 2> /dev/null
#  mv ${PREFIX}_nw output/${PREFIX}_nw_ava_norules
  # AvA with rules
  echo -n "  AvA (with rules)"
  python -m nightwatch.main $I_ARGS input/$API.ava.nw.c $OTHER_ARGS > output/$API.ava.out 2> /dev/null
  mv ${PREFIX}_nw output/${PREFIX}_nw_ava
  echo

  diff -U 15 -u output/$API.ava.out output/$API.lapis.out > output/$API.diff
  diff -U 15 -p -u output/${PREFIX}_nw_ava output/${PREFIX}_nw_lapis > output/$API.generated.diff

  head -n 1 output/$API.ava*.out
  echo
  echo "==> output/$API.lapis.out <=="
  head -n 3 output/$API.lapis.out
}

run_api mvnc mvnc
run_api cuda cu
#run_api cuda cu cuda.more.lapis