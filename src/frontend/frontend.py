from dash import Dash, html, dcc, Input, Output, callback, State
import pandas
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
import tpt

tp_test = None

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = Dash(__name__, external_stylesheets=external_stylesheets)

data = pandas.read_csv('https://plotly.github.io/datasets/country_indicators.csv')


app.layout = html.Div([
    html.H1("Open Triple Pulse Test", style={'textAlign': 'center'}),
    html.Div([
        html.H3("Inputs to the TPT"),
        html.Div([
            html.Div([
                html.H6("Effective Area: ", style={'width': '49%', 'display': 'inline-block'}),
                dcc.Input(
                    id='input-effective_area',
                    type='number',
                    value=35,
                    style={'width': '30%', 'display': 'inline-block', 'font-size': '18px'}
                ),
                html.H6(" mm²", style={'width': '10%', 'display': 'inline-block', 'margin-left': '1%'}),
            ]),
            html.Div([
                html.H6("Number Turns: ", style={'width': '49%', 'display': 'inline-block'}),
                dcc.Input(
                    id='input-number_turns',
                    type='number',
                    value=5,
                    style={'width': '30%', 'display': 'inline-block', 'font-size': '18px'}
                ),
            ]),
            html.Div([
                html.H6("B peak to peak: ", style={'width': '49%', 'display': 'inline-block'}),
                dcc.Input(
                    id='input-magnetic_flux_density_ac_peak_to_peak',
                    type='number',
                    value=200,
                    style={'width': '30%', 'display': 'inline-block', 'font-size': '18px'}
                ),
                html.H6(" mT", style={'width': '10%', 'display': 'inline-block', 'margin-left': '1%'}),
            ]),
            html.Div([
                html.H6("B DC bias: ", style={'width': '49%', 'display': 'inline-block'}),
                dcc.Input(
                    id='input-magnetic_flux_density_dc_bias',
                    type='number',
                    value=200,
                    style={'width': '30%', 'display': 'inline-block', 'font-size': '18px'}
                ),
                html.H6(" mT", style={'width': '10%', 'display': 'inline-block', 'margin-left': '1%'}),
            ]),
            html.Div([
                html.H6("Frequency: ", style={'width': '49%', 'display': 'inline-block'}),
                dcc.Input(
                    id='input-frequency',
                    type='number',
                    value=100,
                    style={'width': '30%', 'display': 'inline-block', 'font-size': '18px'}
                ),
                html.H6(" kHz", style={'width': '10%', 'display': 'inline-block', 'margin-left': '1%'}),
            ]),
            html.Div([
                html.H6("Inductance: ", style={'width': '49%', 'display': 'inline-block'}),
                dcc.Input(
                    id='input-inductance',
                    type='number',
                    value=1000,
                    style={'width': '30%', 'display': 'inline-block', 'font-size': '18px'}
                ),
                html.H6(" μH", style={'width': '10%', 'display': 'inline-block', 'margin-left': '1%'}),
            ]),
            html.Div([
                html.Button('Run test', id='run-test-button', style={'margin-left': '15%', 'margin-top': '5%', 'width': '25%', 'display': 'inline-block'}),
                html.Div(children="Waiting", id='running', style={'margin-left': '5%', 'margin-top': '5%', 'width': '25%', 'display': 'inline-block', 'color': 'red', 'font-size': '20px'}),
            ]),

        ],
            style={'width': '49%', 'display': 'inline-block'}
        ),

    ], style={'width': '50%', 'display': 'inline-block', 'margin-left': '10%'}),

    html.Div([
        html.H6("Done by:", id="aux", style={'width': '100%', 'display': 'inline-block'}),
        html.H6("Cui, Binyu", style={'width': '100%', 'display': 'inline-block', 'margin-left': '10%'}),
        html.H6("Martinez, Alfonso", style={'width': '100%', 'display': 'inline-block', 'margin-left': '10%'}),
        html.H6("Slama, George", style={'width': '100%', 'display': 'inline-block', 'margin-left': '10%'}),
        html.H6("Wang, Jun", style={'width': '100%', 'display': 'inline-block', 'margin-left': '10%'}),
        html.H6("Wilkowski, Matt", style={'width': '100%', 'display': 'inline-block', 'margin-left': '10%'}),
        html.H6(" ", style={'width': '100%', 'display': 'inline-block'}),
        dcc.Link(href="https://github.com/JunWang-Bristol/TPT-Bristol/tree/open-tpt", style={'width': '100%', 'display': 'inline-block'}),
        html.H6(" ", style={'width': '100%', 'display': 'inline-block'}),
    ], style={'display': 'inline-block', 'width': '30%'}),

    html.Div(children="Core Losses: ", id='core-losses-output', style={'display': 'inline-block', 'width': '70%', 'margin-top': '1%', 'margin-left': '10%', 'margin-right': '10%', 'font-size': '24px'}),
    html.Div([
        dcc.Graph(id='x-time-series'),
    ], style={'display': 'inline-block', 'width': '80%', 'margin-left': '10%', 'margin-right': '10%'}),
])


def create_time_series(data):
    fig = go.Figure()
    print(data)
    fig.add_trace(go.Scatter(x=data['time'], y=data['Input Voltage'], mode='lines', name='Input Voltage'))
    fig.add_trace(go.Scatter(x=data['time'], y=data['Output Voltage'], mode='lines', name='Output Voltage'))
    fig.add_trace(go.Scatter(x=data['time'], y=data['Current'], mode='lines', name='Current'))

    fig.update_xaxes(showgrid=False)

    fig.update_yaxes(type='linear')

    fig.add_annotation(x=0, y=0.85, xanchor='left', yanchor='bottom',
                       xref='paper', yref='paper', showarrow=False, align='left', text='')

    fig.update_layout(height=500, margin={'l': 20, 'b': 30, 'r': 10, 't': 10})

    return fig


@callback(
    Output('running', 'children', allow_duplicate=True),
    Input('run-test-button', 'n_clicks'),
    prevent_initial_call=True
)
def loading(ea):
    return "Running"


@callback(
    Output('core-losses-output', 'children'),
    Output('x-time-series', 'figure'),
    Input('running', 'children'),
    # Input('run-test-button', 'n_clicks'),
    State('input-effective_area', 'value'),
    State('input-number_turns', 'value'),
    State('input-magnetic_flux_density_ac_peak_to_peak', 'value'),
    State('input-magnetic_flux_density_dc_bias', 'value'),
    State('input-frequency', 'value'),
    State('input-inductance', 'value'),
    prevent_initial_call=True
)
def update_x_timeseries(nclicks, effective_area, number_turns, magnetic_flux_density_ac_peak_to_peak, magnetic_flux_density_dc_bias, frequency, inductance):
    global tp_test
    print(f"tp_test: {tp_test}")

    if tp_test is None:
        with open(os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(__file__), os.pardir, os.pardir, "hardware_configuration.json"))) as f:
            configuration = json.load(f)
            print(configuration)

        tp_test = tpt.TPT(
            **configuration
        )
        tp_test.set_timeout_in_ms(5000)
        tp_test.set_maximum_voltage_error(0.1)

    effective_area = effective_area / 1000000
    magnetic_flux_density_ac_peak_to_peak = magnetic_flux_density_ac_peak_to_peak / 1000
    magnetic_flux_density_dc_bias = magnetic_flux_density_dc_bias / 1000
    frequency = frequency * 1000
    inductance = inductance / 1000000
    print("update_x_timeseries")
    print(f"effective_area: {effective_area}")
    print(f"number_turns: {number_turns}")
    print(f"magnetic_flux_density_ac_peak_to_peak: {magnetic_flux_density_ac_peak_to_peak}")
    print(f"magnetic_flux_density_dc_bias: {magnetic_flux_density_dc_bias}")
    print(f"frequency: {frequency}")
    print(f"inductance: {inductance}")

    measure_parameters = tpt.TPT.MeasureParameters(
        effective_area=effective_area,
        number_turns=number_turns,
        magnetic_flux_density_ac_peak_to_peak=magnetic_flux_density_ac_peak_to_peak,
        magnetic_flux_density_dc_bias=magnetic_flux_density_dc_bias,
        frequency=frequency,
        inductance=inductance,
    )
    print(f"measure_parameters.effective_area: {measure_parameters.effective_area}")
    print(f"measure_parameters.number_turns: {measure_parameters.number_turns}")
    print(f"measure_parameters.magnetic_flux_density_ac_peak_to_peak: {measure_parameters.magnetic_flux_density_ac_peak_to_peak}")
    print(f"measure_parameters.magnetic_flux_density_dc_bias: {measure_parameters.magnetic_flux_density_dc_bias}")
    print(f"measure_parameters.frequency: {measure_parameters.frequency}")
    print(f"measure_parameters.inductance: {measure_parameters.inductance}")
    core_losses, data = tp_test.run_test(measure_parameters)
    print("core_losses")
    print(core_losses)
    print("data")
    print(data)
    return f"Core Losses: {core_losses} W", create_time_series(data)


@callback(
    Output('running', 'children', allow_duplicate=True),
    Input('core-losses-output', 'children'),
    prevent_initial_call=True
)
def not_loading(ea):
    return "Waiting"


if __name__ == '__main__':
    app.run(debug=True)
