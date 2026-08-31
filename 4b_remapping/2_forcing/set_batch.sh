export BASIN_TASK=/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/multibasin_preprocessing_MERIT_72.txt
export MONTH_TASK=/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/setmonth_tasks_MERIT_72.txt

export NBASIN=$(wc -l < "$BASIN_TASK")
export NMONTH=$(wc -l < "$MONTH_TASK")
