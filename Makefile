.PHONY: help install dev run test test-cov lint demo clean

help:
	@echo "Valido — perintah yang tersedia:"
	@echo "  make install   Pasang dependensi runtime"
	@echo "  make dev       Pasang dependensi + alat pengembangan"
	@echo "  make run       Jalankan aplikasi Streamlit (http://localhost:8501)"
	@echo "  make test      Jalankan seluruh test pytest"
	@echo "  make test-cov  Jalankan test dengan laporan cakupan"
	@echo "  make lint      Periksa gaya kode dengan ruff"
	@echo "  make demo      Buat data contoh lalu audit lewat CLI"
	@echo "  make clean     Hapus cache dan hasil audit"

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

run:
	streamlit run app.py

test:
	python -m pytest

test-cov:
	python -m pytest --cov=valido --cov-report=term-missing

lint:
	ruff check .

demo:
	python scripts/make_sample_data.py
	python cli.py audit examples/data/transaksi_penjualan.xlsx --config configs/contoh_aturan_transaksi.yaml --out hasil --profile

clean:
	rm -rf hasil hasil_csv .pytest_cache .ruff_cache
	find . -name "__pycache__" -type d -exec rm -rf {} +
