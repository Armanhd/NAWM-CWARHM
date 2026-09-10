export BASIN_TASK=/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/multibasin_preprocessing_CAN_04CA003_05CA009.txt
export MONTH_TASK=/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/month_tasks_CAN_04CA003_05CA009.txt

export NBASIN=$(wc -l < "$BASIN_TASK")
export NMONTH=$(wc -l < "$MONTH_TASK")
