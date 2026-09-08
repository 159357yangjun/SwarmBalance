3 qmix_u
python src/main.py --config=qmix --env-config=env_drone with unique_task_assignment=True evaluate=True checkpoint_path="results\models\qmix__2026-06-07_15-46-54" test_nepisode=10 batch_size_run=1 use_cuda=False save_model=False

4 vdn_u
python src/main.py --config=vdn --env-config=env_drone with unique_task_assignment=True evaluate=True checkpoint_path="results\models\vdn__2026-06-07_15-48-20" load_step=65000 test_nepisode=10 batch_size_run=1 use_cuda=False save_model=False


5 iql_u
python src/main.py --config=iql --env-config=env_drone with unique_task_assignment=True evaluate=True checkpoint_path="results\models\iql__2026-06-07_17-05-32" load_step=100000 test_nepisode=10 batch_size_run=1 use_cuda=False save_model=False

6 qmix
python src/main.py --config=qmix --env-config=env_drone with unique_task_assignment=False evaluate=True checkpoint_path="results\models\qmix__2026-06-07_17-06-06" load_step=150000 test_nepisode=10 batch_size_run=1 use_cuda=False save_model=False

8 vdn
python src/main.py --config=vdn --env-config=env_drone with unique_task_assignment=False evaluate=True checkpoint_path="results\models\vdn__2026-06-07_21-47-16" load_step=116503 test_nepisode=10 batch_size_run=1 use_cuda=False save_model=False

9 iql
python src/main.py --config=iql --env-config=env_drone with unique_task_assignment=False evaluate=True checkpoint_path="results\models\iql__2026-06-07_21-47-26" test_nepisode=10 batch_size_run=1 use_cuda=False save_model=False

