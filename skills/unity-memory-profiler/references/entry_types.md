# Unity Memory Profiler .snap Entry Types

Complete list of 76 entry types in index order. The index determines the chapter position in the directory.

| Idx | Entry Name | Format |
|-----|-----------|--------|
| 0 | Metadata_Version | SingleValue |
| 1 | Metadata_RecordDate | SingleValue |
| 2 | Metadata_UserMetadata | SingleValue |
| 3 | Metadata_CaptureFlags | SingleValue |
| 4 | Metadata_VirtualMachineInformation | SingleValue |
| 5 | NativeTypes_Name | DynamicSizeArray |
| 6 | NativeTypes_NativeBaseTypeArrayIndex | ConstantSizeArray |
| 7 | NativeObjects_NativeTypeArrayIndex | ConstantSizeArray |
| 8 | NativeObjects_HideFlags | ConstantSizeArray |
| 9 | NativeObjects_Flags | ConstantSizeArray |
| 10 | NativeObjects_InstanceId | ConstantSizeArray |
| 11 | NativeObjects_Name | DynamicSizeArray |
| 12 | NativeObjects_NativeObjectAddress | ConstantSizeArray |
| 13 | NativeObjects_Size | ConstantSizeArray |
| 14 | NativeObjects_RootReferenceId | ConstantSizeArray |
| 15 | GCHandles_Target | ConstantSizeArray |
| 16 | Connections_From | ConstantSizeArray |
| 17 | Connections_To | ConstantSizeArray |
| 18 | ManagedHeapSections_StartAddress | ConstantSizeArray |
| 19 | ManagedHeapSections_Bytes | DynamicSizeArray |
| 20 | ManagedStacks_StartAddress | ConstantSizeArray |
| 21 | ManagedStacks_Bytes | DynamicSizeArray |
| 22 | TypeDescriptions_Flags | ConstantSizeArray |
| 23 | TypeDescriptions_Name | DynamicSizeArray |
| 24 | TypeDescriptions_Assembly | DynamicSizeArray |
| 25 | TypeDescriptions_FieldIndices | DynamicSizeArray |
| 26 | TypeDescriptions_StaticFieldBytes | DynamicSizeArray |
| 27 | TypeDescriptions_BaseOrElementTypeIndex | ConstantSizeArray |
| 28 | TypeDescriptions_Size | ConstantSizeArray |
| 29 | TypeDescriptions_TypeInfoAddress | ConstantSizeArray |
| 30 | TypeDescriptions_TypeIndex | ConstantSizeArray |
| 31 | FieldDescriptions_Offset | ConstantSizeArray |
| 32 | FieldDescriptions_TypeIndex | ConstantSizeArray |
| 33 | FieldDescriptions_Name | DynamicSizeArray |
| 34 | FieldDescriptions_IsStatic | ConstantSizeArray |
| 35 | NativeRootReferences_Id | ConstantSizeArray |
| 36 | NativeRootReferences_AreaName | DynamicSizeArray |
| 37 | NativeRootReferences_ObjectName | DynamicSizeArray |
| 38 | NativeRootReferences_AccumulatedSize | ConstantSizeArray |
| 39 | NativeAllocations_MemoryRegionIndex | ConstantSizeArray |
| 40 | NativeAllocations_RootReferenceId | ConstantSizeArray |
| 41 | NativeAllocations_AllocationSiteId | ConstantSizeArray |
| 42 | NativeAllocations_Address | ConstantSizeArray |
| 43 | NativeAllocations_Size | ConstantSizeArray |
| 44 | NativeAllocations_OverheadSize | ConstantSizeArray |
| 45 | NativeAllocations_PaddingSize | ConstantSizeArray |
| 46 | NativeMemoryRegions_Name | DynamicSizeArray |
| 47 | NativeMemoryRegions_ParentIndex | ConstantSizeArray |
| 48 | NativeMemoryRegions_AddressBase | ConstantSizeArray |
| 49 | NativeMemoryRegions_AddressSize | ConstantSizeArray |
| 50 | NativeMemoryRegions_FirstAllocationIndex | ConstantSizeArray |
| 51 | NativeMemoryRegions_NumAllocations | ConstantSizeArray |
| 52 | NativeMemoryLabels_Name | DynamicSizeArray |
| 53 | NativeAllocationSites_Id | ConstantSizeArray |
| 54 | NativeAllocationSites_MemoryLabelIndex | ConstantSizeArray |
| 55 | NativeAllocationSites_CallstackSymbols | DynamicSizeArray |
| 56 | NativeCallstackSymbol_Symbol | ConstantSizeArray |
| 57 | NativeCallstackSymbol_ReadableStackTrace | DynamicSizeArray |
| 58 | NativeObjects_GCHandleIndex | ConstantSizeArray |
| 59 | ProfileTarget_Info | SingleValue |
| 60 | ProfileTarget_MemoryStats | SingleValue |
| 61 | NativeMemoryLabels_Size | ConstantSizeArray |
| 62 | SceneObjects_Name | DynamicSizeArray |
| 63 | SceneObjects_Path | DynamicSizeArray |
| 64 | SceneObjects_AssetPath | DynamicSizeArray |
| 65 | SceneObjects_BuildIndex | ConstantSizeArray |
| 66 | SceneObjects_RootIdCounts | ConstantSizeArray |
| 67 | SceneObjects_RootIdOffsets | ConstantSizeArray |
| 68 | SceneObjects_RootIds | ConstantSizeArray |
| 69 | NativeMemoryLabels_AllocatorIdentifier | ConstantSizeArray |
| 70 | NativeGfxResourceReferences_Id | ConstantSizeArray |
| 71 | NativeGfxResourceReferences_Size | ConstantSizeArray |
| 72 | NativeGfxResourceReferences_RootId | ConstantSizeArray |
| 73 | NativeAllocatorInfo_AllocatorName | DynamicSizeArray |
| 74 | NativeAllocatorInfo_Identifier | ConstantSizeArray |
| 75 | NativeAllocatorInfo_UsedSize | ConstantSizeArray |
| 76 | NativeAllocatorInfo_ReservedSize | ConstantSizeArray |
| 77 | NativeAllocatorInfo_OverheadSize | ConstantSizeArray |
| 78 | NativeAllocatorInfo_PeakUsedSize | ConstantSizeArray |
| 79 | NativeAllocatorInfo_AllocationCount | ConstantSizeArray |
| 80 | NativeAllocatorInfo_Flags | ConstantSizeArray |
| 81 | ObjectMetaData_MetaDataBufferIndex | ConstantSizeArray |
| 82 | ObjectMetaData_MetaDataBuffer | DynamicSizeArray |
| 83 | SystemMemoryRegions_Address | ConstantSizeArray |
| 84 | SystemMemoryRegions_Size | ConstantSizeArray |
| 85 | SystemMemoryRegions_ResidentSize | ConstantSizeArray |
| 86 | SystemMemoryRegions_Type | ConstantSizeArray |
| 87 | SystemMemoryRegions_Name | DynamicSizeArray |

## Data Type Interpretation

### ConstantSizeArray numeric reading
- `entry_size = 4`: read as `uint32` (little-endian `<I`)
- `entry_size = 8`: read as `uint64` (little-endian `<Q`)
- `entry_size = 2`: read as `uint16` (little-endian `<H`)
- `entry_size = 1`: read as `uint8` (`B`)
- For signed integers (like NativeTypeArrayIndex): read as `int32` (`<i`)

### DynamicSizeArray string reading
Each entry is a variable-length byte sequence. Decode as UTF-8 with `errors='replace'`. Strip null terminators.

### Size entries (NativeObjects_Size, NativeGfxResourceReferences_Size)
Read as unsigned integers. NativeObjects_Size uses the entry_size from the chapter header (typically 8 bytes = uint64). GFX sizes are also uint64.
