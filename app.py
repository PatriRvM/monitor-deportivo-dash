import os
import dash
from dash import dcc, html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from flask import request, jsonify
from flask import send_file
from flask import session
from db import (
    init_db, register_user, authenticate_user,
    save_questionnaire, get_questionnaire_history,
    get_training_load_history, compute_acwr,
    save_sensor_data, get_sensor_history,
    get_athletes_by_sport,export_user_data_csv
)
from questionnaires import QUESTIONNAIRES, get_questionnaire_list, render_questionnaire_form
from sensors import parse_csv_contents, load_ecg_and_compute_bpm, process_imu

# ==========================================================
# INIT
# ==========================================================
init_db()
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.CYBORG])
server = app.server

# ==========================================================
# LAYOUTS DE CONTENIDO
# ==========================================================

def login_layout():
    return dbc.Container([
        html.H2("💃 Monitor de Bailarines", className="text-info text-center mt-5"),
        dbc.Tabs([
            dbc.Tab(label="Entrar", children=[
                dbc.Card(dbc.CardBody([
                    dbc.Input(id={"type": "auth-input", "field": "user"}, placeholder="Usuario", className="mb-2"),
                    dbc.Input(id={"type": "auth-input", "field": "pass"}, type="password", placeholder="Contraseña"),
                    dbc.Button("Iniciar Sesión", id={"type": "auth-btn", "action": "login"}, color="primary", className="w-100 mt-3"),
                ]), className="p-3 border-top-0")
            ]),
            dbc.Tab(label="Registro", children=[
                dbc.Card(dbc.CardBody([
                    dbc.Input(id={"type": "reg-input", "field": "user"}, placeholder="Nuevo Usuario", className="mb-2"),
                    dbc.Input(id={"type": "reg-input", "field": "pass"}, type="password", placeholder="Contraseña", className="mb-2"),
                    dbc.Select(id={"type": "reg-input", "field": "rol"}, options=[
                        {"label": "Bailarín", "value": "deportista"},
                        {"label": "Coreógrafo", "value": "entrenador"}
                    ], value="deportista"),
                    dbc.Button("Crear Cuenta", id={"type": "auth-btn", "action": "reg"}, color="success", className="w-100 mt-3"),
                ]), className="p-3 border-top-0")
            ])
        ], style={"maxWidth": "400px", "margin": "auto"})
    ], fluid=True)

def dancer_view(sess):
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Div(id="status-alert-area"),
                dbc.Card([
                    dbc.CardHeader("🧩 Cuestionarios"),
                    dbc.CardBody([
                        dcc.Checklist(
                            id="q-check",
                            options=[{"label": q["title"], "value": q["id"]} for q in get_questionnaire_list()],
                            value=["general"]
                        ),
                        html.Div(id="q-forms"),
                        dbc.Button("Guardar Datos", id="save-q-btn", color="success", className="mt-3 w-100"),
                        html.Div(id="q-msg-dancer")
                    ])
                ]),

                # Botón para exportar datos
                dbc.Card([
                    dbc.CardHeader("💾 Exportar Datos"),
                    dbc.CardBody([
                        dbc.Button("Descargar CSV", id="export-btn", color="info", className="w-100"),
                        html.Div(id="export-msg", className="mt-2")
                    ])
                ], className="mt-2"),
                dbc.Card([
    dbc.CardHeader("📥 Importar Datos"),
    dbc.CardBody([
        dcc.Upload(
            id="import-upload",
            children=dbc.Button(
                "Subir CSV",
                color="secondary",
                className="w-100"
            ),
            multiple=False
        ),
        html.Div(id="import-msg", className="mt-2")
    ])
], className="mt-2"),                
            ], md=4),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("📡 Sensores Live"),
                    dbc.CardBody([
                        dcc.Graph(id="bpm-graph", style={"height": "230px"}),
                        dcc.Graph(id="imu-graph", style={"height": "230px"}),
                        dcc.Graph(id="questionnaire-graph", style={"height": "250px"})
                    ])
                ])
            ], md=8)
        ])
    ], fluid=True)

def coach_view():
    athletes = get_athletes_by_sport("baile")
    return dbc.Container([
        html.H4("Panel Coreógrafo", className="text-info"),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="coach-athlete-select", 
                                 options=[{"label": a["username"], "value": a["id"]} for a in athletes],
                                 placeholder="Seleccionar bailarín"), md=4),
        ], className="mb-3"),
        dbc.Row([
            # IDs CORREGIDOS PARA COINCIDIR CON LOS CALLBACKS
            dbc.Col(dbc.Card([dbc.CardHeader("Carga"), dbc.CardBody(dcc.Graph(id="coach-load-graph"))]), md=6),
            dbc.Col(dbc.Card([dbc.CardHeader("BPM"), dbc.CardBody(dcc.Graph(id="coach-bpm-graph"))]), md=6)
        ])
    ], fluid=True)

# ==========================================================
# ROOT LAYOUT
# ==========================================================
app.layout = html.Div([
    dcc.Store(id="session", storage_type="local"),
    dcc.Interval(id="auto-refresh", interval=3000), 
    html.Div(id="navbar-container"),
    html.Div(id="global-msg-container", style={"maxWidth": "400px", "margin": "auto"}),
    html.Div(id="page-content")
])



import plotly.graph_objects as go

def calculate_user_risk(user_id):
    """
    Devuelve: "safe", "warning" o "danger"
    Basado solo en BPM y actividad
    """

    data = get_sensor_history(user_id)

    if not data:
        return "safe"

    last = data[-1]   # último registro

    bpm = last.get("bpm")

    if bpm is None:
        return "safe"

    if bpm > 120 or bpm < 45:
        return "danger"

    if bpm > 100 or bpm < 55:
        return "warning"

    return "safe"



def make_bpm_figure(df):
    if df is None or df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["bpm"],
        mode="lines+markers",
        name="BPM"
    ))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=230
    )
    return fig


def make_imu_figure(df):
    if df is None or df.empty:
        return go.Figure()

    accel = (df["accel_x"]**2 + df["accel_y"]**2 + df["accel_z"]**2) ** 0.5

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=accel,
        mode="lines+markers",
        name="Aceleración"
    ))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=230
    )
    return fig


def make_questionnaire_figure(user_id):
    df = get_questionnaire_history(user_id)

    if df is None or df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["score"],
        mode="lines+markers",
        name="Cuestionarios"
    ))

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=250
    )

    return fig


def build_status_alert(user_id):
    risk = calculate_user_risk(user_id)

    if risk == "danger":
        return dbc.Alert("🔴 RIESGO", color="danger")
    elif risk == "warning":
        return dbc.Alert("🟠 PRECAUCIÓN", color="warning")
    else:
        return dbc.Alert("🟢 ESTABLE", color="success")




# ==========================================================
# CALLBACKS NAVEGACIÓN Y AUTH
# ==========================================================

@app.callback(
    [Output("page-content", "children"), Output("navbar-container", "children"), Output("global-msg-container", "children", allow_duplicate=True)],
    [Input("session", "data")],
    prevent_initial_call=True
)
def display_page(sess):
    if not sess: return login_layout(), "", ""
    nav = dbc.NavbarSimple(
        brand=f"Monitor 💃 | {sess['username']}",
        children=[dbc.Button("Salir", id={"type": "auth-btn", "action": "logout"}, color="danger", size="sm")],
        color="dark", dark=True, className="mb-4"
    )
    view = coach_view() if sess.get("rol") == "entrenador" else dancer_view(sess)
    return view, nav, ""

@app.callback(
    [Output("session", "data", allow_duplicate=True), Output("global-msg-container", "children", allow_duplicate=True)],
    [Input({"type": "auth-btn", "action": ALL}, "n_clicks")],
    [State({"type": "auth-input", "field": ALL}, "value"), State({"type": "reg-input", "field": ALL}, "value")],
    prevent_initial_call=True
)
def handle_auth(n_clicks, login_vals, reg_vals):
    if not ctx.triggered_id or not any(x for x in n_clicks if x): return no_update
    action = ctx.triggered_id["action"]
    if action == "logout": return None, dbc.Alert("Sesión cerrada", color="info")
    if action == "login":
        u, p = login_vals[0], login_vals[1]
        res = authenticate_user(u, p)
        if res:
            res.update({"username": u, "user_id": res["id"]})
            return res, ""
        return no_update, dbc.Alert("Datos incorrectos", color="danger")
    if action == "reg":
        u, p, r = reg_vals[0], reg_vals[1], reg_vals[2]
        if register_user(u, p, 25, "baile", r): return no_update, dbc.Alert("✅ Registrado", color="success")
        return no_update, dbc.Alert("❌ Error", color="danger")
    return no_update, no_update

# ==========================================================
# CALLBACKS DATOS (BAILARÍN)
# ==========================================================

@app.callback(
    [Output("q-msg-dancer", "children"), Output("status-alert-area", "children")],
    Input("save-q-btn", "n_clicks"),
    [State("q-check", "value"), State({"type": "q-field", "qid": ALL, "key": ALL}, "value"), State("session", "data")],
    prevent_initial_call=True
)
def save_dancer_data(n, qs, vals, sess):
    if not n or not sess: return no_update, no_update, no_update
    it = iter(vals); fatiga = 0; uid = sess["user_id"]
    for q in qs:
        resp = {f["key"]: next(it, None) for f in QUESTIONNAIRES[q]["fields"]}
        if "fatiga" in resp: fatiga = float(resp["fatiga"] or 0)
        save_questionnaire(uid, q, resp)
    alert = dbc.Alert("🟢 ÓPTIMO", color="success") if fatiga < 5 else dbc.Alert("🔴 RIESGO", color="danger")
    
    return dbc.Alert("Guardado", color="success", duration=2000), alert

@app.callback(
    [Output("bpm-graph", "figure"), Output("imu-graph", "figure")],
    [Input("auto-refresh", "n_intervals"), Input("session", "data")]
)
def update_dancer_plots(n, sess):
    # SEGURIDAD: Solo ejecutar si el rol es deportista
    if not sess or sess.get("rol") != "deportista": return go.Figure(), go.Figure()
    df = pd.DataFrame(get_sensor_history(sess["user_id"]))
    f_bpm = go.Figure(); f_imu = go.Figure()
    if not df.empty:
        ts = pd.to_datetime(df.timestamp)
        f_bpm.add_trace(go.Scatter(x=ts, y=df.bpm, name="BPM", line_color="red"))
        if "accel_x" in df.columns:
            mag = (df.accel_x**2 + df.accel_y**2 + df.accel_z**2)**0.5
            f_imu.add_trace(go.Scatter(x=ts, y=mag, name="IMU", line_color="orange"))
    f_bpm.update_layout(template="plotly_dark", title="Pulso Live"); f_imu.update_layout(template="plotly_dark", title="IMU Live")
    return f_bpm, f_imu

@app.callback(
    Output("questionnaire-graph", "figure"),
    [Input("auto-refresh", "n_intervals"), Input("session", "data")]
)
def update_questionnaire_graph(n, sess):
    if not sess or sess.get("rol") != "deportista":
        return go.Figure()

    data = get_questionnaire_history(sess["user_id"], days=30)

    if not data:
        return go.Figure()

    df = pd.DataFrame([
        {"timestamp": d["timestamp"], **d["responses"]}
        for d in data
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    fig = go.Figure()

    for col in ["fatiga", "rpe", "horas", "energia"]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["timestamp"],
                y=df[col],
                mode="lines+markers",
                name=col.capitalize()
            ))

    fig.update_layout(
        template="plotly_dark",
        title="Evolución Cuestionarios",
        margin=dict(l=10, r=10, t=40, b=10),
        legend_title="Variables"
    )

    return fig

@app.callback(
    Output("export-msg", "children"),
    Input("export-btn", "n_clicks"),
    State("session", "data"),
    prevent_initial_call=True
)
def export_user_data(n, sess):
    if not n or not sess:
        return no_update
    
    try:
        path = export_user_data_csv(sess["user_id"])
        # Link de descarga
        return dbc.Alert(
            html.A("✅ Descarga lista", href=f"/{path}", target="_blank", style={"color": "white"}),
            color="success"
        )
    except Exception as e:
        return dbc.Alert(f"❌ Error exportando: {e}", color="danger")
    


@app.callback(
    Output("import-msg", "children"),
    Input("import-upload", "contents"),
    State("import-upload", "filename"),
    prevent_initial_call=True
)
def import_sensor_data(contents, filename):
    try:
        if contents is None:
            raise dash.exceptions.PreventUpdate

        df = parse_csv_contents(contents, filename)

        if df is None or df.empty:
            return dbc.Alert("❌ Archivo vacío o inválido", color="danger")

        required = {"timestamp", "bpm", "hrv", "accel_x", "accel_y", "accel_z"}
        if not required.issubset(df.columns):
            return dbc.Alert("❌ El CSV no tiene las columnas necesarias", color="danger")

        user_id = session.get("user_id")

        for _, row in df.iterrows():
            save_sensor_data(
                user_id=user_id,
                bpm=row["bpm"],
                hrv=row["hrv"],
                accel={
                    "x": row["accel_x"],
                    "y": row["accel_y"],
                    "z": row["accel_z"]
                },
                gyro=None
            )

        return dbc.Alert(f"✅ {len(df)} registros importados correctamente", color="success")

    except Exception as e:
        print("❌ Error importando:", e)
        return dbc.Alert(f"❌ Error importando: {str(e)}", color="danger")







# ==========================================================
# CALLBACKS COREÓGRAFO (CORREGIDO ID)
# ==========================================================

@app.callback(
    [Output("coach-load-graph", "figure"), Output("coach-bpm-graph", "figure")],
    [Input("coach-athlete-select", "value"), Input("auto-refresh", "n_intervals")],
    [State("session", "data")]
)
def update_coach_view(athlete_id, n, sess):
    # SEGURIDAD: Solo ejecutar si el rol es entrenador
    if not sess or sess.get("rol") != "entrenador" or not athlete_id: 
        return go.Figure(), go.Figure()
    
    l_df = pd.DataFrame(get_training_load_history(athlete_id))
    s_df = pd.DataFrame(get_sensor_history(athlete_id))
    fig1 = go.Figure(); fig2 = go.Figure()
    
    if not l_df.empty: 
        fig1.add_trace(go.Scatter(x=pd.to_datetime(l_df.timestamp), y=l_df.load, line_color="cyan"))
    if not s_df.empty: 
        fig2.add_trace(go.Scatter(x=pd.to_datetime(s_df.timestamp), y=s_df.bpm, line_color="red"))
        
    fig1.update_layout(template="plotly_dark", title="Historial Carga"); fig2.update_layout(template="plotly_dark", title="Historial BPM")
    return fig1, fig2

# ==========================================================
# API SIMULADOR Y Q-FORMS
# ==========================================================
@server.route("/api/send_sensor_data", methods=["POST"])
def api_sensor():
    data = request.get_json()
    save_sensor_data(user_id=data["user_id"], source="Sim", bpm=data.get("bpm"),
                     accel_x=(data.get("accel") or {}).get("x"), accel_y=(data.get("accel") or {}).get("y"), accel_z=(data.get("accel") or {}).get("z"))
    return jsonify({"status": "ok"})



@server.route("/data/<path:filename>")
def download_file(filename):
    try:
        return send_file(f"data/{filename}", as_attachment=True)
    except Exception as e:
        return f"❌ Error: {e}", 404


@app.callback(Output("q-forms", "children"), Input("q-check", "value"))
def render_q(qs): return [render_questionnaire_form(q) for q in qs] if qs else ""

if __name__ == "__main__":

    app.run(debug=True, port=8050)
