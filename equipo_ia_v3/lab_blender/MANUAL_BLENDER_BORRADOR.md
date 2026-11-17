# Manual de Blender para el banco (BORRADOR, sin validar)

Estado: borrador. Hay que validarlo ejecutando cada ejemplo dentro de Blender con el ejecutor antes de usarlo en una
tanda. No contiene la solución de ninguna tarea de `tareas.py`: solo recetas generales.

## 1. Primitivas (crear una pieza)
- Cubo: `bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))`. `size=1` da un cubo de 1 m de lado.
- Cilindro: `bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1, location=(x, y, z))`. Está centrado en su
  posición, así que apoyado en el suelo su centro está a `depth / 2` de altura.
- Esfera: `bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(x, y, z))`.
- Tras crear, la pieza activa está en `ob = bpy.context.active_object`. Ponle nombre con `ob.name = "..."`.

## 2. Tamaño y posición
- Para cambiar el tamaño a posteriori: `ob.scale = (a, b, c)`. Las medidas «a × b × c» son en X, Y, Z.
- Para mover: `ob.location = (x, y, z)`. Z es hacia arriba.
- Una caja de tamaño `(a, b, c)` con centro en `(x, y, z)` tiene su base en `z - c / 2`.

## 3. Jerarquía (una pieza unida a otra)
- `bpy.context.view_layer.update()` antes de emparentar, para que las matrices estén al día.
- `hijo.parent = padre`
- `hijo.matrix_parent_inverse = padre.matrix_world.inverted()`
- Así el hijo conserva su posición en el mundo y se mueve con el padre.

## 4. Animación por fotogramas
- Rango: `sc = bpy.context.scene; sc.frame_start, sc.frame_end = 1, 48`
- Fotograma inicial: `sc.frame_set(1)`, pon la posición, y luego `ob.keyframe_insert(data_path="location", frame=1)`.
- Fotograma final: `sc.frame_set(48)`, pon la nueva posición, y `ob.keyframe_insert(data_path="location", frame=48)`.
- Rotación: igual con `data_path="rotation_euler"`.

## 5. Materiales y color
- `m = bpy.data.materials.new("Nombre"); m.use_nodes = True`
- `m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (r, g, b, 1.0)`
- `ob.data.materials.append(m)`
- Ojo: en Blender 5.2 el color que ve el render es el de Base Color del Principled BSDF. `diffuse_color` solo afecta
  a la vista en pantalla.

## 6. Armaduras (esqueleto con huesos)
- `arm = bpy.data.armatures.new("Nombre"); rig = bpy.data.objects.new("Nombre", arm)`
- Enlazar al escenario: `bpy.context.collection.objects.link(rig)`
- Editar huesos: `bpy.context.view_layer.objects.active = rig` y `bpy.ops.object.mode_set(mode="EDIT")`
- Hueso nuevo: `hueso = arm.edit_bones.new("Nombre")`, con `hueso.head = (x, y, z)` y `hueso.tail = (x, y, z)`
- Al terminar: `bpy.ops.object.mode_set(mode="OBJECT")`

## 7. Errores que más se repiten
- Un objeto recién creado es el activo solo justo después de su `primitive_*_add`; guarda la referencia en una
  variable en ese momento.
- Usa exactamente los nombres pedidos en la tarea; el verificador los busca por nombre.
- No añadas cámara, luz ni suelo si la tarea no lo pide: la escena empieza vacía.
- No guardes `bpy.ops` en variables; llámalo de forma directa.
