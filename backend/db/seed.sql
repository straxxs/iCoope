USE icoope;

INSERT INTO categoria (nombre, descripcion) VALUES
('Útiles', 'Cuadernos, lapiceras y más'),
('Uniformes', 'Chombas y buzos'),
('Eventos', 'Entradas y rifas');

INSERT INTO espacio (nombre, descripcion) VALUES
('Salón de actos', 'Capacidad 200 personas'),
('Patio', 'Patio central'),
('Buffet', NULL);

INSERT INTO producto (id_categoria, nombre, descripcion, precio) VALUES
(1, 'Cuaderno A4 rayado', 'Tapa dura, 80 hojas', 3500.00),
(2, 'Chomba del colegio', 'Algodón piqué', 18000.00);

INSERT INTO producto
    (id_categoria, nombre, descripcion, precio, es_evento, fecha_evento)
VALUES
(3, 'Rifa anual', 'Un número para la rifa', 2000.00, TRUE, '2026-12-10 18:00:00'),
(3, 'Fiesta de la primavera', 'Entrada general', 5000.00, TRUE, '2026-12-15 20:00:00');

INSERT INTO variante_producto (id_producto, nombre, stock) VALUES
(1, 'Único', 50),
(2, 'Talle 8', 10),
(2, 'Talle 10', 10),
(2, 'Talle 12', 3),
(3, 'General', 100),
(4, 'General', 150);