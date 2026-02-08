# Importación de Cotizaciones desde PDF

Este módulo permite importar cotizaciones masivamente desde archivos PDF (remisiones, entregas, etc.) utilizando reconocimiento de texto y búsqueda difusa (fuzzy match) para identificar clientes, ubicaciones y productos.

## Características

-   **Reconocimiento Inteligente**: Extrae tablas de PDFs detectando columnas automáticamente.
-   **Búsqueda Difusa**: Encuentra clientes, ubicaciones y productos aunque los nombres en el PDF tengan errores tipográficos o variaciones leves.
-   **Validación Visual**: Semáforo de colores (Verde/Amarillo/Rojo) para identificar rápidamente registros listos, advertencias y errores.
-   **Auto-corrección**: Opciones para crear ubicaciones faltantes, asignar ubicaciones a clientes y crear nuevos clientes automáticamente.
-   **Agrupación Flexible**: Genera una orden por línea, una por cliente, o agrupada por cliente y ubicación.

## Instalación

Este módulo requiere las siguientes librerías de Python:

```bash
pip install pdfplumber thefuzz
```

## Uso

1.  Vaya a **Ventas > Órdenes > Cotizaciones**.
2.  Haga clic en el botón **"Importar PDF"** ubicado en el encabezado de la lista o en el menú de acción.
3.  Suba su archivo PDF.
4.  El sistema procesará el archivo y mostrará una previsualización de los datos detectados.
5.  Revise las líneas:
    -   **Verde**: Todo correcto.
    -   **Amarillo**: Requiere atención (ej. ubicación nueva, asignación pendiente). Puede usar el botón "Resolver" o habilitar las opciones de creación automática.
    -   **Rojo**: Error crítico (ej. producto no encontrado). Puede editar manualmente la línea para seleccionar el registro correcto.
6.  Seleccione el **Modo de Agrupación** deseado (recomendado: "Agrupar por Cliente y Ubicación").
7.  Haga clic en **"Importar Cotizaciones"**.

## Formato del PDF

El módulo intenta ser flexible, pero para mejores resultados el PDF debe contener una tabla con encabezados identificables:
-   **Cliente**: Palabras clave: "Cliente", "Customer", "Señor(es)".
-   **Ubicación**: Palabras clave: "Ubicación", "Obra", "Proyecto", "Destino".
-   **Producto**: Palabras clave: "Producto", "Descripción", "Item".
-   **Cantidad**: Palabras clave: "Cantidad", "Cant", "Qty".

## Configuración y Acceso

Solo los usuarios con permisos de **Sales Manager** pueden acceder al asistente de importación.
