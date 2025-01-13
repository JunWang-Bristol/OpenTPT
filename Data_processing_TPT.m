clear all
close all

% ------------------------------------------------------------------
% Input the desired file name to save the results of this analysis
% ------------------------------------------------------------------
xlsname = 'BH_Q_uJ_UT900';

%% Test setup input

% --------------------------------
% Method 1: Set up the database
% --------------------------------
% N1_database = {23,23,10,7,5,6,7,7}; %Primary winding number    
% N2_database = {23,23,10,7,5,6,7,7}; %Secondary winding number 
% le_database = {250e-3,198e-3,255.3e-3,174.2e-3,82.06e-3,54.2e-3,60.2e-3,43.6e-3};  %Average magnetic path length for iron powder in m
% Se_database = {346e-6,338e-6,267.2e-6,288.3e-6,82.6e-6,26.17e-6,48.9e-6,33.6e-6}; %Cross-section area of iron powder in m^2
% Ve_database = {86.4e-6,67e-6,68.2e-6,50.2e-6,6.778e-6,1.417e-6,2.942e-6,1.465e-6};

% Material_type = 3;
% N1 = N1_database{Material_type};
% N2 = N2_database{Material_type};
% le = le_database{Material_type};
% Se = Se_database{Material_type};
% Ve = Ve_database{Material_type};

% -------------------------
% Method 2: Assign values
% -------------------------
N1 = 12;
N2 = 12;
le = 267e-3;
Se = 437e-6;
Ve = 858e-6;

%% Determine the file path

% -------------------
% Set default path
% -------------------
if (exist('recentpath.mat','file'))
    load('recentpath')
else
    recentpath = 'E:\OneDrive\PhD\Safran\InductorTest\DataProcess\*.csv';
end

% --------------------
% Determine csv path
% --------------------
[filename,pathname] = uigetfile(recentpath,...
    'Please select a designated waveform csv file', 'MultiSelect','on');
if isequal(filename,0)
    error('Aborted by user');
else
    if iscell(filename)
        files = cell2mat(strcat(filename,', '));
        files(end) = '.';
    else
        files = filename;
    end
    disp(['Plotting file ''' pathname '']);
    disp(['          ' files])
    recentpath = [pathname '*.csv'];
    save('recentpath','recentpath') % update path for next run
end

%% Read csv data

TestData=csvread([pathname filename],2,0);
t  = TestData(:,1);    % First colum is time in seconds
% t = t*(1e-09); 
Upri = TestData(:,2);  % Current probe 1 in Amps % 4
Usec = TestData(:,2);  % Voltage probe 2 in Volts measuring secondary winding open-circuit voltage % 3
Usec = round(Usec,8);
I = TestData(:,3);     % Current probe 1 in Amps
I = round(I,8);

%% Compensate the measurement bias

% ---------------------------------------------------------------------
% Subtracts the mean of the first 50 samples from voltage and current
% waveforms, which compensates for any offset present in raw data.
% ---------------------------------------------------------------------

% ---------------------------------------------------------
% Optional: V=0 at the beginning, otherwise comment below
% ---------------------------------------------------------
Comp_index = 50;
Uprizero = mean(Upri(1:Comp_index));
Useczero = mean(Usec(1:Comp_index));
Izero = mean(I(1:Comp_index));

Upri = Upri-Uprizero;
Usec = Usec-Useczero;
I = I-Izero;

% --------------------------------------------------------------
% Optional：flip the voltage waveform, otherwise comment below
% --------------------------------------------------------------
% Usec = -Usec;

%% Window smoothing for current

% ------------------------------------------------------
% Smooth current and voltage with a 10-sample average
% ------------------------------------------------------

for i = 1:1:length(I)-3
    I(i) = I(i+3);
end

counter = 10;
for i = 1:1:length(I)-counter
    Avg_First = mean(I(i:i+counter));
    I(i) = Avg_First;
end

for v = 1:1:length(Usec)-counter
    v_Avg_First = mean(Usec(v:v+counter));
    Usec(v) = v_Avg_First;
end

%% Data calculation

% ------------------
% Calculate H & B
% ------------------

Ins_H  = N1*I/le;
Ins_dB = Usec/(N2*Se);
for xx = 1: 1 : length(Ins_dB)
  Ins_B(xx,1) = trapz(t(1:xx),Ins_dB(1:xx),1);
end

%% User interface to obtain the cycle t1-t2

% -------------------------------------------------------------------------
% Find negative and positive peaks in current, and calculate on/off times 
% within one cycle.
% -------------------------------------------------------------------------

[row,col] = find(Usec>0.5,1); % Detection of the first rising edge
t_H0start_index = row;

% ---------------------------------------
% Find negative peaks in stable periods
% ---------------------------------------
[pks,neg_locs] = findpeaks(-Ins_B,'MinPeakProminence',0.0001); % If detected interval not correct, try change the location of peaks
num_neg_locs = length(neg_locs); % Total number of negative peak indices
half_index = floor(num_neg_locs / 2); 
t1_index = neg_locs(half_index,1);
t2_index = neg_locs(half_index+1,1);

% -----------------------------------------
% Find a positive peak in the same period
% -----------------------------------------
[pks,pos_locs] = findpeaks(Ins_B,'MinPeakProminence',0.0001);
t_H0end_index = pos_locs(1,1);
t12_index = NaN;
for i = 1:length(pos_locs)
    if pos_locs(i) > t1_index && pos_locs(i) < t2_index
        t12_index = pos_locs(i); % Positive peak in the same cycle
        break; % Stop after finding the first valid positive peak
    end
end

% ----------------------------------------------------------
% Adjust negative peaks if no valid positive peak is found
% ----------------------------------------------------------
if isnan(t12_index)
    warning('No positive peak found in the current cycle. Adjusting indices...');
    % Shift to the next cycle
    if num_neg_locs > half_index+2
        t1_index = neg_locs(half_index+1,1); % Next cycle first negative peak
        t2_index = neg_locs(half_index+2,2); % Next cycle second negative peak
        for i = 1:length(pos_locs)
            if pos_locs(i) > t1_index && pos_locs(i) < t2_index
                t12_index = pos_locs(i); % Positive peak in the adjusted cycle
                break;
            end
        end
    else
        error('Not enough negative peaks to adjust.');
    end
end

t_on = t(t12_index)-t(t1_index);
t_off = t(t2_index)-t(t12_index);

%% Plot compensated UI curve

% ------------------------------------------------------------------
% Figure 1: Plot I and V over time on dual y-axes with timestamps
% ------------------------------------------------------------------

Fig_UI_calibrated = figure;
yyaxis left;
plot(t, I,'LineWidth', 1);
ylabel('I - A','FontSize', 16);
grid on;
hold on;
plot(t(t_H0start_index),I(t_H0start_index),'rv','MarkerFaceColor','r')
text(t(t_H0start_index),I(t_H0start_index),'H0_1')
plot(t(t12_index),I(t12_index),'rv','MarkerFaceColor','r')
text(t(t12_index),I(t12_index),'H0_2')
plot(t(t1_index),I(t1_index),'rv','MarkerFaceColor','r')
text(t(t1_index),I(t1_index),'P1')
plot(t(t12_index),I(t12_index),'rv','MarkerFaceColor','y')
text(t(t12_index),I(t12_index),'P2')
plot(t(t2_index),I(t2_index),'rv','MarkerFaceColor','b')
text(t(t2_index),I(t2_index),'P3')
yyaxis right;
plot(t,Usec,'LineWidth', 1);
ylabel('U - v','FontSize', 16);
hold off;
xlabel('t - s','FontSize', 16);
title('Voltage vs Current Time Graph');
movegui(Fig_UI_calibrated,'southeast');

%% Calculation by integration

Usec_plus_int = trapz(t(t1_index:t12_index),Usec(t1_index:t12_index));   % Secondary positive voltage averaged
Usec_minus_int = trapz(t(t12_index:t2_index),Usec(t12_index:t2_index));

Usec_plus = Usec_plus_int/t_on;   % Secondary positive voltage averaged
Usec_minus = Usec_minus_int/t_off;  % Secondary negative voltage averaged

Upri_plus_int = trapz(t(t1_index:t12_index),Upri(t1_index:t12_index));   % Secondary positive voltage averaged
Upri_minus_int = trapz(t(t12_index:t2_index),Upri(t12_index:t2_index));

Upri_plus = Upri_plus_int/t_on;   % Secondary positive voltage averaged
Upri_minus = Upri_minus_int/t_off;  % Secondary negative voltage averaged

PRD_plus = t(t12_index)-t(t1_index);      % Secondary positive voltage duration averaged
PRD_minus = t(t2_index)-t(t12_index);     % Secondary negative voltage duration averaged


%% Generate B-H curve

% ---------------------------------
% Calculate H and B for B-H curve
% ---------------------------------

H = N1*I((t1_index):(t2_index),1)/le; % no shifted
t_t1t2 = t(t1_index:t2_index,1);
PRD_BH = t(t2_index)-t(t1_index);
Freq = 1/PRD_BH;
t_H0 = t(t_H0end_index)-t(t_H0start_index);
U_t1t2 = Usec(t1_index:t2_index,1);
I_t1t2 = I(t1_index:t2_index,1);
VI_loss = trapz(U_t1t2(1:1:length(U_t1t2)),I_t1t2(1:1:length(I_t1t2)));
H0 = N1/le*(I(t12_index,1)-I(t1_index,1)+I(t12_index,1)-I(t2_index,1))/4+N1/le*I(t1_index,1);
B = Ins_B(t1_index:t2_index);
delta_B = double(max(B)-min(B));
B0 = double(min(B)+delta_B/2);
delta_H = double(max(H)-min(H));
dB_dt = delta_B/((t_on+t_off)/2);
I_avg = I(t12_index)-(I(t12_index)-I(t2_index))/2;

%% Plot hysteresis area

% -----------------------------------
% Connect the first and last point
% -----------------------------------

B(length(B)) = B(1);
H(length(H)) = H(1);
B_plot = B(1:2:end);
H_plot = H(1:2:end);

Shys = trapz(B(1:1:length(B)),H(1:1:length(H)));    % Area of the minor loop in the unit of J/m3
Qloss = Se*le*Shys;                                 % From the B-H curve

% --------------------------
% Figure 2: Plot B-H Curve
% --------------------------

Fig_HB_loop = figure;
plot(H_plot,B_plot*1000,'r');
hold on;
grid on;
xlabel('H - A/m');
ylabel('B - mT');
title('B-H Curve');
movegui(Fig_HB_loop,'southwest');
hold off;

% ----------------------------------------------
% Figure 3: Plot B-H Curve with key parameters
% ----------------------------------------------

Fig_HB = figure;
plot(H,B,'r');
hold on;
plot(Ins_H,Ins_B,'LineStyle',':','Color','k');
xlabel('H - A/m');
ylabel('B - T');
title({['B-H Curve'];['H0 = ',num2str(H0,4),' A/m, B0 = ',num2str(B0*1000,4),' mT, ','Freq = ',num2str(Freq,6),' Hz']; ...
    ['\DeltaB_{pktopk} = ',num2str(delta_B*1000,3),' mT, \DeltaH = ',num2str(delta_H,4), ' A/m, \DeltaB/\Deltat = ',num2str(dB_dt,4), ' T/s'];['ton = ',num2str(t_on*1000000,4),' us, toff = ',num2str(t_off*1000000,4), 'us']; ...
    ['Upri_p = ',num2str(Upri_plus,3),' V, Upri_m = ',num2str(Upri_minus,3), ' V, I bias = ',num2str(I_avg,3),' A']; ...
    [ 'Q = ',num2str(Qloss*1e6,3),' uJ  UT plus = ',num2str(Upri_plus_int*1e6), 'Vus UT minus = ',num2str(Upri_minus_int*1e6),'Vus']});
movegui(Fig_HB,'northwest');
hold off;

% -----------------------------------------------------
% Figure 4: Plot B waveform over time with timestamps
% -----------------------------------------------------

Fig_InsB = figure;
plot(t,Ins_B*1000);
hold on;
plot(t(t1_index),Ins_B(t1_index)*1000,'rv','MarkerFaceColor','r')
text(t(t1_index),Ins_B(t1_index)*1000,'P1')
plot(t(t12_index),Ins_B(t12_index)*1000,'rv','MarkerFaceColor','y')
text(t(t12_index),Ins_B(t12_index)*1000,'P2')
plot(t(t2_index),Ins_B(t2_index)*1000,'rv','MarkerFaceColor','b')
text(t(t2_index),Ins_B(t2_index)*1000,'P3')
ylabel({'B - mT'});
xlabel('t - s');
title('B with Highlighted Peaks');
movegui(Fig_InsB,'northeast');

%% Plot VI loop

% ------------------------------------------
% Figure 5: Plot V (integration) - I curve
% ------------------------------------------

for xx = 1: 1 : length(Usec)
  U_int(xx,1) = trapz(t(1:xx)*1e6,Usec(1:xx),1);
end
U_int_inex = U_int(t1_index:t2_index);
I_temp = I(t1_index:t2_index);

Fig_VI =figure;
plot (I_temp,U_int_inex);
xlabel('Current - A');
ylabel('Voltage Integral - \muVs');
title('Voltage integration vs Current');
movegui(Fig_VI, 'west');