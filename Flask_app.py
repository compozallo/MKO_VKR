from flask import Flask, render_template, request, jsonify
import socket
import numpy as np
from MKO_opt import ParetoOptimizer
import os

app = Flask(__name__)
optimizer = ParetoOptimizer()
selected_point = None

#port = int(os.environ.get("PORT", 5000))
#app.run(host="0.0.0.0", port=port)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

@app.route('/move_point', methods=['POST'])
def move_point():
    global selected_point
    data = request.get_json()
    x = float(data['x'])
    y = float(data['y'])
    selected_point = (x, y)
    optimizer.selected_point = selected_point  # обновляем в объекте оптимизатора, если нужно

    idx = optimizer.find_closest_solution(x, y)
    main_plot = optimizer.create_main_plot_json()
    path_plot = optimizer.create_path_plot_json()
    radar_chart = optimizer.create_radar_chart()  # HTML-строка
    detailed = optimizer.get_detailed_recommendations(idx)
    general = optimizer.get_general_recommendations(idx)

    return jsonify({
        'main_plot': main_plot,
        'path_plot': path_plot,
        'radar_chart': radar_chart,  # HTML строка, не JSON
        'detailed': detailed,
        'general': general
    })

@app.route('/', methods=['GET', 'POST'])
def index():
    global selected_point
    default_values = {
        'Давление на выходе (атм) ↑': 10,
        'Износ оборудования (%) ↓ [0-100]': 30,
        'Затраты на ТО (руб/ч) ↓': 500,
        'Возраст оборудования (лет) ↓': 5,
        'Общая эффективность ↑': 70,
        'Требуемая производительность (т/ч) ↑': 50
    }
    num_solutions = 500

    if request.method == 'POST':
        form = request.form
        inputs = {k: float(form.get(k, default_values[k])) for k in default_values}
        num_solutions = int(form.get('num_solutions', 500))
        for name in optimizer.pumps:
            optimizer.toggle_pump(name, form.get(f"{name}_enabled") == 'on')
            for param in optimizer.pumps[name]:
                if param not in ['Включен', 'Название']:
                    field = f"{name}_{param}"
                    if field in form:
                        optimizer.pumps[name][param] = float(form.get(field))

        optimizer.generate_solutions(num_solutions, inputs)
        optimizer.set_required_productivity(inputs['Требуемая производительность (т/ч) ↑'])
        selected_point = None
        optimizer.selected_point = None

    return render_template('main_template.html',
        criteria_names=optimizer.criteria_names,
        default_values=default_values,
        num_solutions=num_solutions,
        pumps=optimizer.pumps,
        main_plot=optimizer.create_main_plot_json(),
        path_plot=optimizer.create_path_plot_json(),
        radar_chart=optimizer.create_radar_chart() if optimizer.current_values else None,
        general_recommendations=optimizer.get_general_recommendations() if optimizer.current_values else [],
        detailed_recommendations=[],
        forecast_recommendations=optimizer.get_forecast_recommendations() if optimizer.current_values else [],
        forecast_table=optimizer.get_forecast_table_html()
    )

if __name__ == '__main__':
    #port = int(os.environ.get("PORT", 5000))
    #app.run(host="0.0.0.0", port=port, debug=True)
    ip = get_local_ip()
    print(f"Запущено на http://{ip}:1500")
    app.run(host=ip, port=1500, debug=True)