from bd_config import obtener_catalogo_libros

if __name__ == "__main__":
    catalogo = obtener_catalogo_libros()
    print(f"\n✅ LIBROS ACTIVOS Y DEPURADOS EN LA BASE DE DATOS ({len(catalogo)} manuales):\n")
    for libro in catalogo:
        print(f"- [{libro['categoria']:<16}] ({libro['idioma']}) {libro['fuente']} ({libro['total_bloques']} bloques)")
