export BASIN_TASK=/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/multibasin_preprocessing_CAN_01AD003_01FB001.txt
export MONTH_TASK=/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/month_tasks_CAN_01AD003_01FB001.txt
export NBASIN=$(wc -l < "$BASIN_TASK")
export NMONTH=$(wc -l < "$MONTH_TASK")
