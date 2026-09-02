from citylearn.citylearn import CityLearnEnv

schema = 'citylearn_challenge_2022_phase_all_plus_evs'

env = CityLearnEnv(schema, central_agent=True, episode_time_steps=48, render_mode='none')
observations, _ = env.reset()
while not env.terminated:
    actions = [env.action_space[0].sample()]
    observations, reward, terminated, truncated, info = env.step(actions)

class _Model:
    pass
#D:\Users\clfbe\anaconda3\envs\cl2\lib\site-packages\outputs\ui_exports\
model = _Model()
model.env = env

env.export_final_kpis(model, filepath='exported_kpis.csv')
print('Render folder:', env.new_folder_path)