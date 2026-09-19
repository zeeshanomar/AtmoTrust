# Five-minute demo

1. Start the local production server and open `http://127.0.0.1:8000` in two browser windows. Replay runs automatically at 1×; both windows show the same advancing source time. Pause before setting up a precise fault if desired.
2. In **Simulation Lab**, use the default Chandigarh temperature Spike, +9 °C, one sample; click **Inject All**. The next automatic frame updates both windows. While paused, use **Next frame** once.
3. In **Investigation**, select Chandigarh temperature. Read the observed/expected/peer chart, Trust Score, confidence, severity, probable pattern, and evidence.
4. In **Maintenance**, acknowledge the new issue and inspect its health trend and recommendation.
5. **Reset** returns to the warmed baseline paused. Start **Regional Weather Change**, play or step two frames, and inspect the network. Inject a separate Chandigarh spike during the event; process one frame and show the isolated fault.
6. Switch to **Genuine live**; the provider is fetched immediately. Show its timestamps if available, or the explicit degraded state. With live values available, a scheduled fault and **Next frame** show RAW LIVE versus TEST COPY. Switch back to Replay and reset. Repeat the flow without restarting either window.

If tiles fail, the map retains positioned markers. If live data fails, Replay remains independent. If the backend restarts, refresh both windows to join the new disposable run.
